import re
import threading

from .contracts import Translation
from .models import MATH, ModelError, validate_language


TOKEN = re.compile(r"\[\[TUTOR_MATH_\d+\]\]")


class Localizer:
    def __init__(self, store, provider):
        self.store = store
        self.provider = provider
        self.lock = threading.Lock()

    def render(self, views: list[tuple[dict, str, str]], target: str):
        groups = {}
        for obj, field, source in views:
            text = obj.get(field)
            if source != target and text:
                groups.setdefault(source, set()).add(text)
        if not groups:
            return
        with self.lock:
            translations = {}
            for source, texts in groups.items():
                translations.update(((source, text), translated) for text, translated in (
                    self._translate(source, target, sorted(texts)).items()
                ))
        for obj, field, source in views:
            if (source, obj.get(field)) in translations:
                obj[field] = translations[source, obj[field]]

    def _translate(self, source, target, texts):
        cached = {}
        with self.store.connect() as db:
            for text in texts:
                row = db.execute(
                    "SELECT translation FROM translations WHERE source_locale = ? AND target_locale = ? AND source = ?",
                    (source, target, text),
                ).fetchone()
                if row:
                    cached[text] = row["translation"]
        missing = [text for text in texts if text not in cached]
        for index in range(0, len(missing), 18):
            batch = missing[index:index + 18]
            masks = []
            math = []
            for text in batch:
                pieces = []

                def mask(match):
                    pieces.append(match.group())
                    return f"[[TUTOR_MATH_{len(pieces) - 1}]]"

                masks.append(MATH.sub(mask, text))
                math.append(pieces)
            result = self.provider.generate(
                "translate",
                "Translate texts in the same order, one translation per input. Preserve all "
                "[[TUTOR_MATH_n]] placeholders exactly. Preserve meaning, numbers, logical conditions, "
                "option distinctions and technical terminology. Do not add hints or evidence.",
                {"locale": target, "sourceLocale": source, "texts": masks}, Translation,
            )
            if len(result.texts) != len(batch):
                raise ModelError("invalid_model_output")
            validate_language(result.texts, target)
            rows = []
            for original, translated, slots in zip(batch, result.texts, math, strict=True):
                if not translated.strip() or not len(translated) <= max(1200, len(original) * 5):
                    raise ModelError("invalid_model_output")
                expected = [f"[[TUTOR_MATH_{i}]]" for i in range(len(slots))]
                if sorted(TOKEN.findall(translated)) != sorted(expected):
                    raise ModelError("invalid_model_output")
                for marker, piece in zip(expected, slots, strict=True):
                    translated = translated.replace(marker, piece)
                cached[original] = translated
                rows.append((source, target, original, translated))
            with self.store.connect(write=True) as db:
                db.executemany("INSERT OR IGNORE INTO translations VALUES (?, ?, ?, ?)", rows)
        return cached
