#!/usr/bin/env python3
"""
extract.py — Parse Cambridge syllabus PDFs into structured JSON.

Supports O Level (5070) and AS & A Level (9701) Chemistry layouts.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "sources"
INTERMEDIATE = Path(__file__).resolve().parent / "intermediate"

MAIN_TOPICS: list[tuple[int, str]] = [
    (1, "States of matter"),
    (2, "Atoms, elements and compounds"),
    (3, "Stoichiometry"),
    (4, "Electrochemistry"),
    (5, "Chemical energetics"),
    (6, "Chemical reactions"),
    (7, "Acids, bases and salts"),
    (8, "The Periodic Table"),
    (9, "Metals"),
    (10, "Chemistry of the environment"),
    (11, "Organic chemistry"),
    (12, "Experimental techniques and chemical analysis"),
]

MAIN_TOPIC_BY_NORM = {
    re.sub(r"\s+", " ", name.lower().strip()): num
    for num, name in MAIN_TOPICS
}

VERB_STARTS = (
    "state ", "describe ", "define ", "calculate ", "identify ", "explain ",
    "understand ", "use ", "draw ", "write ", "interpret ", "predict ", "construct ",
    "relate ", "compare ", "distinguish ", "show ", "determine ", "deduce ",
    "suggest ", "evaluate ", "outline ", "list ", "name ", "give ", "add ",
    "remove ", "measure ", "record ", "observe ", "test ", "investigate ",
    "classify ", "select ", "apply ", "convert ", "balance ", "complete ",
    "label ", "analyse ", "analyze ", "devise ", "recognise ", "recognize ",
)

SKIP_RE = [
    re.compile(r"^Cambridge O Level", re.I),
    re.compile(r"^Cambridge International AS", re.I),
    re.compile(r"^syllabus for \d{4}", re.I),
    re.compile(r"^www\.cambridgeinternational", re.I),
    re.compile(r"^Back to contents page", re.I),
    re.compile(r"^Subject content\s*$", re.I),
    re.compile(r"^AS Level subject content", re.I),
    re.compile(r"^A Level subject content", re.I),
    re.compile(r"^Physical chemistry\s*$", re.I),
    re.compile(r"^Inorganic chemistry\s*$", re.I),
    re.compile(r"^Organic chemistry\s*$", re.I),
    re.compile(r"^Analysis\s*$", re.I),
    re.compile(r"^Learning outcomes\s*$", re.I),
    re.compile(r"^Candidates should be able to:?\s*$", re.I),
    re.compile(r"^This syllabus gives", re.I),
    re.compile(r"^Where appropriate", re.I),
    re.compile(r"^Scientific subjects", re.I),
    re.compile(r"^Practical work", re.I),
    re.compile(r"^develop ", re.I),
    re.compile(r"^use equipment", re.I),
    re.compile(r"^study\.", re.I),
    re.compile(r"^complying with", re.I),
    re.compile(r"^allows them", re.I),
    re.compile(r"^•"),
    re.compile(r"^appreciate how", re.I),
    re.compile(r"^transfer the", re.I),
    re.compile(r"^e\.g\.", re.I),
    re.compile(r"^or \[Ar\]", re.I),
    re.compile(r"^assessed\.\s*$", re.I),
    re.compile(r"^continued\s*$", re.I),
    re.compile(r"^\d{1,2}\s*$"),
    re.compile(r"^Grade descriptions", re.I),
    re.compile(r"^Details of the assessment", re.I),
    re.compile(r"^In \d+\.\d+", re.I),
]

SUBTOPIC_RE = re.compile(r"^(\d{1,2}\.\d{1,2})\s+(.+)$")
CONTINUED_RE = re.compile(r"^(\d{1,2}\.\d{1,2})\s+(.+?)\s+continued\s*$", re.I)
NUMBERED_ITEM_RE = re.compile(r"^(\d{1,2})\s+(.+)$")
VALID_SUBTOPIC_RE = re.compile(r"^\d{1,2}\.\d{1,2}$")


def normalize(line: str) -> str:
    line = line.replace("\x07", " ").replace("\u2002", " ").replace("\u2009", " ").replace("\u00a0", " ")
    line = re.sub(r"\s+", " ", line).strip()
    return line


def is_valid_subtopic_code(code: str) -> bool:
    if not VALID_SUBTOPIC_RE.match(code):
        return False
    major, minor = (int(x) for x in code.split("."))
    return 1 <= major <= 30 and 1 <= minor <= 99


def should_skip(line: str) -> bool:
    if not line:
        return True
    if re.fullmatch(r"\d{1,2}", line):
        return True
    if re.fullmatch(r"[\d.]+", line):
        return True
    if re.search(r"to \d+\.\d+\)", line) and len(line) < 20:
        return True
    return any(p.search(line) for p in SKIP_RE)


def norm_title(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().strip())


def match_main_topic(line: str) -> int | None:
    key = norm_title(line)
    if key in MAIN_TOPIC_BY_NORM:
        return MAIN_TOPIC_BY_NORM[key]
    for num, name in MAIN_TOPICS:
        if norm_title(name) in key or key in norm_title(name):
            return num
    return None


def objective_body(line: str) -> str:
    line = normalize(line)
    numbered = NUMBERED_ITEM_RE.match(line)
    if numbered:
        return numbered.group(2).strip()
    return line


def is_objective_start(line: str) -> bool:
    body = objective_body(line).lower()
    if re.match(r"^\([a-z]\)\s*", body):
        return True
    return body.startswith(VERB_STARTS)


def is_continuation(line: str) -> bool:
    if not line:
        return False
    if SUBTOPIC_RE.match(line) or CONTINUED_RE.match(line):
        return False
    if NUMBERED_ITEM_RE.match(line):
        return False
    if match_main_topic(line):
        return False
    if try_dynamic_main_topic(line):
        return False
    return True


def find_pdf() -> Path:
    pdfs = sorted(SOURCES.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDF found in {SOURCES}")
    return pdfs[0]


def try_dynamic_main_topic(line: str) -> tuple[int, str] | None:
    m = re.match(r"^(\d{1,2})\s+([A-Za-z][A-Za-z0-9 ,()&'\-/]+)$", line)
    if not m or SUBTOPIC_RE.match(line) or CONTINUED_RE.match(line):
        return None
    if is_objective_start(line):
        return None
    num = int(m.group(1))
    name = m.group(2).strip()
    if num < 1 or num > 30 or len(name) < 4 or len(name) > 120:
        return None
    if name.lower().startswith(VERB_STARTS):
        return None
    return num, name


def _looks_like_objective_tail(text: str) -> bool:
    lower = text.lower()
    return lower.startswith(VERB_STARTS) or bool(re.match(r"^\([a-z]\)", lower))


def preprocess_raw_lines(raw_lines: list[str]) -> list[str]:
    """Merge PDF line breaks (tabs / split headings) into parseable lines."""
    merged: list[str] = []
    i = 0
    while i < len(raw_lines):
        line = normalize(raw_lines[i])
        if not line:
            i += 1
            continue

        sub_only = re.match(r"^(\d{1,2}\.\d{1,2})\s*$", line)
        if sub_only and i + 1 < len(raw_lines):
            nxt = normalize(raw_lines[i + 1])
            if nxt and not re.match(r"^\d", nxt) and "Learning outcomes" not in nxt:
                merged.append(f"{sub_only.group(1)} {nxt}")
                i += 2
                continue

        num_only = re.match(r"^(\d{1,2})\s*$", line)
        if num_only and i + 1 < len(raw_lines):
            nxt = normalize(raw_lines[i + 1])
            if nxt and not should_skip(nxt):
                if _looks_like_objective_tail(nxt) or len(nxt.split()) > 8:
                    merged.append(f"{num_only.group(1)} {nxt}")
                    i += 2
                    continue
                if len(nxt.split()) <= 10 and not nxt.lower().startswith(VERB_STARTS):
                    merged.append(f"{num_only.group(1)} {nxt}")
                    i += 2
                    continue

        merged.append(line)
        i += 1
    return merged


def find_content_start(doc: fitz.Document) -> int:
    for i in range(min(80, len(doc))):
        text = doc[i].get_text()
        if re.search(r"1\.1\s+Particles in the atom", text):
            return i
        if re.search(r"1\.1\s+Solids, liquids and gases", text):
            return i
        if "AS Level subject content" in text and re.search(r"\b1\.1\s", text):
            return i
    for i in range(min(60, len(doc))):
        text = doc[i].get_text()
        if re.search(r"\b1\.1\s+\S", text) and "Subject content" in text:
            return i
    return 10


def is_valid_subtopic_title(title: str) -> bool:
    title = title.strip()
    if len(title) < 5:
        return False
    words = title.split()
    if re.fullmatch(r"[A-Z][a-z]?", title):
        return False
    if re.search(r"abundance of \[M", title, re.I):
        return False
    if "\ufffd" in title:
        return False
    if len(words) == 1:
        return len(title) >= 5
    return True


def find_content_end(doc: fitz.Document, start: int) -> int:
    for i in range(start, len(doc)):
        text = doc[i].get_text()
        if "Data section" in text and "Additional information" in text:
            return i
        if re.search(r"^Grade descriptions", text, re.M):
            return i
    return len(doc)


def extract_content_pages(doc: fitz.Document, start: int | None = None, end: int | None = None) -> str:
    if start is None:
        start = find_content_start(doc)
    if end is None:
        end = find_content_end(doc, start)
    else:
        end = min(end, len(doc))
    raw_lines: list[str] = []
    for page_idx in range(start, end):
        raw_lines.extend(doc[page_idx].get_text().splitlines())
    return "\n".join(preprocess_raw_lines(raw_lines))


def parse_syllabus(text: str) -> dict:
    main_topics: list[dict] = []
    subtopics: list[dict] = []
    objectives: list[dict] = []

    current_main: dict | None = None
    current_sub: dict | None = None
    current_obj: dict | None = None
    obj_ordinal = 0

    def flush_objective():
        nonlocal current_obj, obj_ordinal
        if current_obj and current_sub:
            text_body = objective_body(current_obj["text"])
            if text_body and len(text_body) >= 8:
                current_obj["text"] = text_body
                objectives.append(current_obj)
        current_obj = None

    def set_main(number: int, name: str):
        nonlocal current_main, current_sub, obj_ordinal
        flush_objective()
        current_sub = None
        obj_ordinal = 0
        current_main = {"number": number, "name": name}
        if not any(m["number"] == number for m in main_topics):
            main_topics.append(current_main)

    lines = [normalize(ln) for ln in text.splitlines()]
    lines = [ln for ln in lines if not should_skip(ln)]

    started = False

    for line in lines:
        if not started:
            if match_main_topic(line) or SUBTOPIC_RE.match(line) or try_dynamic_main_topic(line):
                started = True
            else:
                continue

        if re.search(r"^Grade descriptions", line, re.I):
            break

        cont = CONTINUED_RE.match(line)
        if cont:
            flush_objective()
            code, title = cont.group(1), cont.group(2).strip()
            if current_sub and current_sub["code"] == code:
                current_sub["title"] = title
            continue

        sub = SUBTOPIC_RE.match(line)
        if sub:
            code, title = sub.group(1), sub.group(2).strip()
            if not is_valid_subtopic_code(code) or not is_valid_subtopic_title(title):
                continue
            if any(s["code"] == code for s in subtopics):
                continue
            flush_objective()
            obj_ordinal = 0
            major = int(code.split(".")[0])
            for mt in main_topics:
                if mt["number"] == major:
                    current_main = mt
                    break
            current_sub = {
                "code": code,
                "title": title,
                "mainTopicNumber": major,
                "mainTopicName": current_main["name"] if current_main else f"Topic {major}",
            }
            subtopics.append(current_sub)
            continue

        main_num = match_main_topic(line)
        if main_num is not None:
            name = next(n for num, n in MAIN_TOPICS if num == main_num)
            set_main(main_num, name)
            continue

        dyn = try_dynamic_main_topic(line)
        if dyn is not None:
            set_main(dyn[0], dyn[1])
            continue

        if current_sub is None:
            continue

        if is_objective_start(line):
            flush_objective()
            obj_ordinal += 1
            current_obj = {
                "code": f"{current_sub['code']}.{obj_ordinal}",
                "ordinal": obj_ordinal,
                "subtopicCode": current_sub["code"],
                "text": line,
            }
        elif current_obj is not None and is_continuation(line):
            current_obj["text"] += " " + line

    flush_objective()

    valid_codes = {s["code"] for s in subtopics if is_valid_subtopic_code(s["code"])}
    subtopics = [s for s in subtopics if s["code"] in valid_codes]
    objectives = [o for o in objectives if o["subtopicCode"] in valid_codes]

    main_by_num = {m["number"]: m["name"] for m in main_topics}
    for s in subtopics:
        s["mainTopicName"] = main_by_num.get(s["mainTopicNumber"], f"Topic {s['mainTopicNumber']}")

    return {"mainTopics": main_topics, "subtopics": subtopics, "objectives": objectives}


def extract_syllabus_from_pdf(pdf_path: Path, spec: str = "") -> dict:
    doc = fitz.open(pdf_path)
    content = extract_content_pages(doc)
    parsed = parse_syllabus(content)
    return {
        "source": pdf_path.name,
        "spec": spec,
        "mainTopicCount": len(parsed["mainTopics"]),
        "subtopicCount": len(parsed["subtopics"]),
        "objectiveCount": len(parsed["objectives"]),
        **parsed,
    }


def main() -> int:
    pdf_path = find_pdf()
    INTERMEDIATE.mkdir(parents=True, exist_ok=True)
    out = extract_syllabus_from_pdf(pdf_path, spec="5070")

    out_path = INTERMEDIATE / "syllabus.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Extracted from {pdf_path.name}:")
    print(f"  {out['mainTopicCount']} main topics")
    print(f"  {out['subtopicCount']} subtopics")
    print(f"  {out['objectiveCount']} learning objectives")
    print(f"  -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
