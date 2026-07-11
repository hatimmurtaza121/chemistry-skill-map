"""Detect syllabus metadata from Cambridge-style PDF cover pages."""

from __future__ import annotations

import re
from pathlib import Path

import fitz

TITLE_INLINE_RE = re.compile(
    r"Cambridge\s+(International\s+)?"
    r"(O\s*Level|IGCSE|AS\s*&\s*A\s*Level|A\s*Level|AS\s*Level)\s+"
    r"([^(\n]+?)\s*\((\d{4})\)",
    re.I,
)
COVER_BLOCK_RE = re.compile(
    r"Cambridge\s+(International\s+)?"
    r"(O\s*Level|IGCSE|AS\s*&\s*A\s*Level|A\s*Level|AS\s*Level)\s*"
    r"(?:\r?\n)+\s*"
    r"([^\n]+?)\s+(\d{4})\b",
    re.I,
)
EXAM_YEARS_RE = re.compile(
    r"(?:for\s+)?(?:examination|exams?)\s+in\s+"
    r"(\d{4})(?:\s*,\s*(\d{4}))?(?:\s+and\s+(\d{4}))?",
    re.I,
)
YEAR_LIKE_RE = re.compile(r"\b(19|20)\d{2}\b")


def _clean_subject(raw: str) -> str:
    subject = re.sub(r"\s+", " ", raw).strip(" -–—")
    subject = re.sub(r"\s+syllabus$", "", subject, flags=re.I).strip()
    return subject or "Syllabus"


def _normalize_level(raw: str) -> str:
    key = re.sub(r"\s+", " ", raw).strip().lower()
    if "as & a" in key or "as and a" in key:
        return "AS & A Level"
    if key.startswith("a level"):
        return "A Level"
    if key.startswith("as level"):
        return "AS Level"
    if "igcse" in key:
        return "IGCSE"
    if "o level" in key:
        return "O Level"
    return raw.strip() or "O Level"


def _year_range_from_match(groups: tuple) -> str | None:
    years = [g for g in groups if g]
    if not years:
        return None
    years = sorted({int(y) for y in years})
    if len(years) == 1:
        return str(years[0])
    return f"{years[0]}–{years[-1]}"


def _years_from_filename(stem: str) -> str | None:
    years = [int(y) for y in YEAR_LIKE_RE.findall(stem)]
    if not years:
        return None
    years = sorted(set(years))
    if len(years) == 1:
        return str(years[0])
    return f"{years[0]}–{years[-1]}"


def _detect_level_on_cover(cover: str) -> str:
    for pattern, label in [
        (r"Cambridge\s+(?:International\s+)?O\s*Level", "O Level"),
        (r"Cambridge\s+(?:International\s+)?IGCSE", "IGCSE"),
        (r"Cambridge\s+International\s+AS\s*&\s*A\s*Level", "AS & A Level"),
        (r"Cambridge\s+(?:International\s+)?AS\s*Level", "AS Level"),
        (r"Cambridge\s+(?:International\s+)?A\s*Level", "A Level"),
    ]:
        if re.search(pattern, cover, re.I):
            return label
    return "O Level"


def _detect_syllabus_form(cover: str) -> str:
    head = cover[:600]
    if re.search(
        r"Cambridge\s+International\s+(?:O\s*Level|IGCSE|AS\s*&\s*A\s*Level|AS\s*Level|A\s*Level)",
        head,
        re.I,
    ):
        return "Cambridge International"
    if re.search(
        r"Cambridge\s+(?:O\s*Level|IGCSE|AS\s*&\s*A\s*Level|AS\s*Level|A\s*Level)",
        head,
        re.I,
    ):
        return "Cambridge"
    if re.search(r"Cambridge\s+International", head, re.I):
        return "Cambridge International"
    return "Cambridge"


def detect_pdf_metadata(pdf_path: Path, *, pdf_name: str = "") -> dict:
    doc = fitz.open(pdf_path)
    cover = doc[0].get_text() if len(doc) else ""
    header = "\n".join(doc[i].get_text() for i in range(min(3, len(doc))))
    stem = Path(pdf_name).stem if pdf_name else pdf_path.stem

    subject = ""
    spec = ""
    level = _detect_level_on_cover(cover)
    syllabus_form = _detect_syllabus_form(cover)
    year_range: str | None = None

    title = TITLE_INLINE_RE.search(cover) or TITLE_INLINE_RE.search(header)
    cover_block = COVER_BLOCK_RE.search(cover) or COVER_BLOCK_RE.search(header)

    if title:
        intl, level_raw, subject_raw, spec_code = title.groups()
        subject = _clean_subject(subject_raw)
        spec = spec_code
        level = _normalize_level(level_raw)
        if intl:
            syllabus_form = "Cambridge International"
    elif cover_block:
        intl, level_raw, subject_raw, spec_code = cover_block.groups()
        subject = _clean_subject(subject_raw)
        spec = spec_code
        level = _normalize_level(level_raw)
        if intl:
            syllabus_form = "Cambridge International"

    if not spec:
        line_match = re.search(r"^(.+?)\s+(\d{4})\s*$", cover, re.I | re.M)
        if line_match and line_match.group(2) != "9001":
            subject = _clean_subject(line_match.group(1))
            spec = line_match.group(2)
        else:
            fn_spec = re.search(r"(?:^|[-_])(\d{4})(?:[-_]|$)", stem)
            if fn_spec:
                spec = fn_spec.group(1)

    if not subject:
        if spec == "5070":
            subject = "Chemistry"
        else:
            subject = _clean_subject(stem.replace(spec, "").replace("-", " ")) if spec else "Syllabus"

    exam_years = EXAM_YEARS_RE.search(cover) or EXAM_YEARS_RE.search(header)
    if exam_years:
        year_range = _year_range_from_match(exam_years.groups())
    if not year_range:
        year_range = _years_from_filename(stem)

    level_label = f"{syllabus_form} {level}".strip()
    base = f"{subject} {spec}".strip() if spec else subject
    display_name = f"{base} — {level_label}"
    if year_range:
        display_name += f" ({year_range})"

    description = f"{syllabus_form} syllabus"
    if year_range:
        description += f" {year_range}"

    return {
        "subject": subject,
        "spec": spec or "0000",
        "level": level,
        "syllabusForm": syllabus_form,
        "yearRange": year_range,
        "displayName": display_name,
        "description": description,
    }
