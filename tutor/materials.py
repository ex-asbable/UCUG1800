import json
import logging
import re

from pypdf import PdfReader

from .contracts import Outline, Source, Topic
from .models import ModelError, validate_language
from .storage import encode, new_id, now


log = logging.getLogger(__name__)
PAGE_LIMIT = 350
PAGE_TEXT_LIMIT = 24_000
OUTLINE_BATCH = 95_000
KEY = re.compile(r"[a-z][a-z0-9_]{1,63}\Z")
TERMS = re.compile(r"[a-zA-Z0-9_]{2,}|[\u3400-\u9fff]")

OUTLINE_RULES = """Create a course outline from the supplied PDF page text. Deduplicate recurring
agenda pages. Group topics by stated or inferred headings and preserve material order.
Reuse existing English snake_case topic keys if the concept still matches. parentKey is
null for top-level topics. For covered topics, use readable sources that actually support
the short explanation and opening question. For explicitly listed but uncovered topics,
use coverage missing, cite only the agenda, and leave explanation and opening empty.
For an essential prerequisite absent from the excerpts, use coverage prerequisite, give
a brief explanation, and cite the later application rather than claiming a definition exists
in the material. Every topic has at least one supplied readable source. Use up to 30 topics.
Leave out headings with no teaching material unless an explicit agenda lists them."""


def read_pdf(path) -> list[tuple[int, str, str]]:
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ModelError("encrypted_pdf")
        if len(reader.pages) > PAGE_LIMIT:
            raise ModelError("too_many_pages")
        result = []
        for number, page in enumerate(reader.pages, 1):
            try:
                content = page.extract_text().replace("\x00", "").strip()[:PAGE_TEXT_LIMIT]
                status = "readable" if content else "unreadable"
            except Exception:
                log.info("Could not extract PDF page %s", number)
                content, status = "", "unreadable"
            result.append((number, content, status))
        return result
    except ModelError:
        raise
    except Exception as error:
        raise ModelError("invalid_pdf") from error


def outline_pages(db, outline_id: str) -> list[dict]:
    outline = db.execute("SELECT material_ids FROM outlines WHERE id = ?", (outline_id,)).fetchone()
    return readable_pages(db, json.loads(outline["material_ids"]))


def readable_pages(db, material_ids: list[str]) -> list[dict]:
    pages = []
    for material_id in material_ids:
        pages.extend(
            {"materialId": material_id, "page": row["number"], "text": row["text"]}
            for row in db.execute(
                "SELECT number, text FROM pages WHERE material_id = ? AND status = 'readable' ORDER BY number",
                (material_id,),
            )
        )
    return pages


def source_ids(pages: list[dict]) -> set[tuple[str, int]]:
    return {(page["materialId"], page["page"]) for page in pages}


def validate_sources(sources: list[Source], allowed: set[tuple[str, int]], *, required: bool = False):
    if len(sources) > 20 or (required and not sources):
        raise ModelError("invalid_citation")
    if any((source.materialId, source.page) not in allowed for source in sources):
        raise ModelError("invalid_citation")


def select_pages(pages: list[dict], query: str, refs: list[dict] | None = None) -> list[dict]:
    terms = set(TERMS.findall(query.casefold()))
    exact = source_ids(refs or [])
    neighbors = {
        (material, page + delta)
        for material, page in exact
        for delta in (-1, 1)
    }

    def rank(page: dict):
        key = (page["materialId"], page["page"])
        matches = terms.intersection(TERMS.findall(page["text"].casefold()))
        relevance = sum(2 if len(term) > 2 else 1 for term in matches)
        return relevance + (26 if key in exact else 4 if key in neighbors else 0)

    return [
        {**page, "text": page["text"][:2500]}
        for page in sorted(pages, key=rank, reverse=True)[:12]
    ]


def topic_version(db, outline_id: str, topic_id: str | None):
    return db.execute(
        """SELECT tv.*, t.key FROM topic_versions tv JOIN topics t ON t.id = tv.topic_id
           WHERE tv.outline_id = ? AND tv.topic_id = ?""", (outline_id, topic_id),
    ).fetchone()


def _validate_topics(topics: list[Topic], pages: list[dict], locale: str):
    allowed = source_ids(pages)
    if not topics or len(topics) > 45:
        raise ModelError("invalid_model_output")
    parents = {topic.key: topic.parentKey for topic in topics}
    if len(parents) != len(topics) or not all(KEY.fullmatch(key) for key in parents):
        raise ModelError("invalid_model_output")
    if not any(topic.coverage != "missing" for topic in topics):
        raise ModelError("invalid_model_output")
    texts = []
    for topic in topics:
        if not topic.title.strip() or len(topic.title) > 220 or len(topic.explanation) > 3600:
            raise ModelError("invalid_model_output")
        if topic.coverage == "missing" and (topic.explanation or topic.opening):
            raise ModelError("invalid_model_output")
        if topic.coverage != "missing" and not (topic.explanation.strip() and topic.opening.strip()):
            raise ModelError("invalid_model_output")
        validate_sources(topic.sources, allowed, required=True)
        seen = {topic.key}
        parent = topic.parentKey
        while parent is not None:
            if parent in seen or parent not in parents:
                raise ModelError("invalid_model_output")
            seen.add(parent)
            parent = parents[parent]
        texts.extend((topic.title, topic.explanation, topic.opening))
    validate_language(texts, locale)


def build_outline(provider, *, name: str, pages: list[dict], old_topics: list[dict], locale: str) -> list[Topic]:
    batches: list[list[dict]] = [[]]
    size = 0
    for page in pages:
        excerpt = page["text"]
        if len(excerpt) > 1400:
            excerpt = f"{excerpt[:1050]}\n[… ]\n{excerpt[-300:]}"
        part = {**page, "text": excerpt}
        length = len(encode(part))
        if size + length > OUTLINE_BATCH:
            batches.append([])
            size = 0
        batches[-1].append(part)
        size += length
    common = {"course": name, "locale": locale, "existingTopics": old_topics}
    drafts = []
    for batch in batches:
        result = provider.generate("outline", OUTLINE_RULES, {**common, "pages": batch}, Outline)
        _validate_topics(result.topics, batch, locale)
        drafts.append(result.topics)
    if len(drafts) == 1:
        return drafts[0]
    referenced = {
        (ref.materialId, ref.page) for draft in drafts for topic in draft for ref in topic.sources
    }
    excerpts = [
        {**page, "text": page["text"][:260]}
        for batch in batches for page in batch
        if (page["materialId"], page["page"]) in referenced
    ]
    result = provider.generate(
        "merge_outline",
        OUTLINE_RULES + " Merge these draft outlines into one. A topic supported in any draft is not missing. "
        "Use only citations in the drafts and the included cited snippets.",
        {
            **common,
            "drafts": [[topic.model_dump() for topic in draft] for draft in drafts],
            "pages": excerpts,
        },
        Outline,
    )
    _validate_topics(result.topics, excerpts, locale)
    return result.topics


def publish_outline(db, course_id: str, material_ids: list[str], topics: list[Topic], locale: str):
    outline_id = new_id()
    db.execute("INSERT INTO outlines VALUES (?, ?, ?, ?)", (outline_id, course_id, encode(material_ids), now()))
    for topic in topics:
        db.execute("INSERT OR IGNORE INTO topics VALUES (?, ?, ?)", (new_id(), course_id, topic.key))
    ids = {row["key"]: row["id"] for row in db.execute("SELECT id, key FROM topics WHERE course_id = ?", (course_id,))}
    for position, topic in enumerate(topics):
        db.execute(
            "INSERT INTO topic_versions VALUES (?, ?, ?, ?, ?, ?)",
            (
                outline_id, ids[topic.key], ids.get(topic.parentKey), position, locale,
                encode(topic.model_dump(exclude={"key", "parentKey"})),
            ),
        )
    db.execute("UPDATE courses SET outline_id = ? WHERE id = ?", (outline_id, course_id))
    return outline_id
