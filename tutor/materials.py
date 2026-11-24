import json
import logging
import posixpath
import re
from pathlib import PurePosixPath
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring
from pypdf import PdfReader

from .contracts import Outline, Source, Topic
from .models import ModelError, validate_language
from .storage import encode, new_id, now


log = logging.getLogger(__name__)
PAGE_LIMIT = 350
PAGE_TEXT_LIMIT = 24_000
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
OUTLINE_BATCH = 95_000
KEY = re.compile(r"[a-z][a-z0-9_]{1,63}\Z")
TERMS = re.compile(r"[a-zA-Z0-9_]{2,}|[\u3400-\u9fff]")

OUTLINE_RULES = """Create a course outline from the supplied course material excerpts. Deduplicate recurring
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


def read_material(path, filename, images=None):
    if filename.lower().endswith(".pdf"):
        return read_pdf(path)
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix in {".docx", ".pptx"}:
        return read_office(path, suffix, images)
    if suffix in {".txt", ".md", ".markdown", ".tex", ".csv", ".tsv", ".rst", ".json", ".xml", ".log"}:
        data = path.read_bytes()
        try:
            text = data.decode("utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
        except UnicodeError as error:
            raise ModelError("invalid_text") from error
        if "\x00" in text:
            raise ModelError("invalid_text")
        return text_sections(text)
    raise ModelError("attachment_only")


def text_sections(text):
    sections = []
    buffer = ""
    for match in re.finditer(r"[^\n]*\n|[^\n]+\Z", text):
        line = match[0]
        if buffer and len(buffer) + len(line) > 6000:
            sections.append(buffer)
            buffer = ""
        if len(line) > 6000:
            if len(sections) + len(line) // 6000 > PAGE_LIMIT:
                raise ModelError("too_many_sections")
            sections.extend(line[start:start + 6000] for start in range(0, len(line), 6000))
        else:
            buffer += line
        if len(sections) > PAGE_LIMIT:
            raise ModelError("too_many_sections")
    if buffer:
        sections.append(buffer)
    return numbered_sections(sections)


def numbered_sections(sections):
    if len(sections) > PAGE_LIMIT:
        raise ModelError("too_many_sections")
    result = []
    for number, section in enumerate(sections, 1):
        text = section.strip()[:PAGE_TEXT_LIMIT]
        result.append((number, text, "readable" if text else "unreadable"))
    return result


def read_office(path, suffix, images=None):
    word = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    slide = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
    drawing = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    relation = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    budget = 64 * 1024 * 1024
    try:
        with ZipFile(path) as archive:
            def xml(name):
                nonlocal budget
                size = archive.getinfo(name).file_size
                budget -= size
                if size > 6 * 1024 * 1024 or budget < 0:
                    raise ModelError("too_many_sections")
                return fromstring(archive.read(name))

            def embedded_images(name, root):
                if images is None:
                    return []
                legacy_image = "{urn:schemas-microsoft-com:vml}imagedata"
                ids = [
                    element.get(relation + ("embed" if element.tag == drawing + "blip" else "id"))
                    for element in root.iter() if element.tag in (drawing + "blip", legacy_image)
                ]
                if not any(ids):
                    return []
                directory, basename = posixpath.split(name)
                relationships = posixpath.join(directory, "_rels", basename + ".rels")
                if relationships not in archive.NameToInfo:
                    return []
                targets = {}
                for item in xml(relationships):
                    if item.get("TargetMode") == "External" or not item.get("Type", "").endswith("/image"):
                        continue
                    target = item.get("Target", "")
                    path = posixpath.normpath(target.lstrip("/") if target.startswith("/")
                                              else posixpath.join(directory, target))
                    if path in archive.NameToInfo and PurePosixPath(path).suffix.lower() in IMAGE_SUFFIXES:
                        targets[item.get("Id")] = path
                return [targets[identifier] for identifier in dict.fromkeys(ids) if identifier in targets]

            if suffix == ".docx":
                name = "word/document.xml"
                document = xml(name)
                paragraphs = list(document.iter(word + "p"))
                texts = ["".join(node.text or "" for node in paragraph.iter(word + "t"))
                         for paragraph in paragraphs]
                pages = text_sections("\n".join(texts))
                for target in embedded_images(name, document):
                    if len(pages) >= PAGE_LIMIT:
                        raise ModelError("too_many_sections")
                    number = len(pages) + 1
                    pages.append((number, "", "unreadable"))
                    images[number] = [target]
                return pages

            presentation = xml("ppt/presentation.xml")
            targets = {item.get("Id"): item.get("Target", "")
                       for item in xml("ppt/_rels/presentation.xml.rels")}
            slide_ids = list(presentation.iter(slide + "sldId"))
            if len(slide_ids) > PAGE_LIMIT:
                raise ModelError("too_many_sections")
            sections = []
            for number, identifier in enumerate(slide_ids, 1):
                target = targets[identifier.get(relation + "id")].removeprefix("/ppt/").removeprefix("slides/")
                if not re.fullmatch(r"slide\d+\.xml", target):
                    raise ModelError("invalid_office")
                name = "ppt/slides/" + target
                root = xml(name)
                if targets_for_slide := embedded_images(name, root):
                    images[number] = targets_for_slide
                sections.append("\n".join("".join(node.text or "" for node in paragraph.iter(drawing + "t"))
                                          for paragraph in root.iter(drawing + "p"))[:PAGE_TEXT_LIMIT])
            return numbered_sections(sections)
    except (BadZipFile, KeyError, ParseError, DefusedXmlException, OSError, RuntimeError, ValueError) as error:
        raise ModelError("invalid_office") from error


def outline_pages(db, outline_id: str, material_id: str | None = None) -> list[dict]:
    if material_id:
        return readable_pages(db, [material_id])
    outline = db.execute("SELECT material_ids FROM outlines WHERE id = ?", (outline_id,)).fetchone()
    return readable_pages(db, json.loads(outline["material_ids"]))


def readable_pages(db, material_ids: list[str]) -> list[dict]:
    pages = []
    for material_id in material_ids:
        for row in db.execute(
            """SELECT p.number, p.text, v.description FROM pages p
               LEFT JOIN page_visuals v USING (material_id, number)
               WHERE p.material_id = ? AND (p.status = 'readable' OR v.description <> '')
               ORDER BY p.number""", (material_id,),
        ):
            page = {"materialId": material_id, "page": row["number"], "text": row["text"]}
            if row["description"]:
                page["visualDescription"] = row["description"]
            pages.append(page)
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
        content = page["text"] + " " + page.get("visualDescription", "")
        matches = terms.intersection(TERMS.findall(content.casefold()))
        relevance = sum(2 if len(term) > 2 else 1 for term in matches)
        return relevance + (26 if key in exact else 4 if key in neighbors else 0)

    return [
        {
            **page, "text": page["text"][:2500],
            **({"visualDescription": page["visualDescription"][:2500]} if "visualDescription" in page else {}),
        }
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
        if "visualDescription" in part:
            part["visualDescription"] = part["visualDescription"][:1500]
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
        {
            **page, "text": page["text"][:260],
            **({"visualDescription": page["visualDescription"][:350]} if "visualDescription" in page else {}),
        }
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


def build_file_outline(db, course_id: str, material_ids: list[str], locale: str) -> list[Topic]:
    materials = {row["id"]: row for row in db.execute(
        "SELECT id, filename, replaces_id FROM materials WHERE course_id = ?", (course_id,),
    )}
    if locale == "en":
        explanation = "This chapter covers one course file. Open the sources or generate a review guide to study it."
        opening = "What part of this file would you like to work through?"
    else:
        explanation = "本章对应一份课件。可以查看原文出处，或生成本章的复习讲解稿。"
        opening = "你想先讨论这份课件里的哪一部分？"
    topics = []
    for material_id in material_ids:
        material = materials[material_id]
        original = material
        while original["replaces_id"]:
            original = materials[original["replaces_id"]]
        pages = readable_pages(db, [material_id])
        indices = sorted({0, len(pages) // 2, len(pages) - 1})
        topics.append(Topic(
            key=f"file_{original['id']}", parentKey=None, title=material["filename"], coverage="supported",
            explanation=explanation, opening=opening,
            sources=[Source(materialId=material_id, page=pages[index]["page"]) for index in indices],
        ))
    return topics


def publish_outline(db, course_id: str, material_ids: list[str], topics: list[Topic], locale: str, *, file_chapters=False):
    outline_id = new_id()
    db.execute("INSERT INTO outlines VALUES (?, ?, ?, ?)", (outline_id, course_id, encode(material_ids), now()))
    for topic in topics:
        db.execute("INSERT OR IGNORE INTO topics VALUES (?, ?, ?)", (new_id(), course_id, topic.key))
    ids = {row["key"]: row["id"] for row in db.execute("SELECT id, key FROM topics WHERE course_id = ?", (course_id,))}
    for position, topic in enumerate(topics):
        content = topic.model_dump(exclude={"key", "parentKey"})
        if file_chapters:
            content["materialId"] = topic.sources[0].materialId
        db.execute(
            "INSERT INTO topic_versions VALUES (?, ?, ?, ?, ?, ?)",
            (
                outline_id, ids[topic.key], ids.get(topic.parentKey), position, locale,
                encode(content),
            ),
        )
    db.execute("UPDATE courses SET outline_id = ? WHERE id = ?", (outline_id, course_id))
    return outline_id
