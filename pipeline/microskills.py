#!/usr/bin/env python3
"""
microskills.py — Decompose syllabus objectives into Marble-style micro-skills.

Each micro-skill is a single teachable, assessable unit with evidence and
assessment prompts. Handles parent/sub-bullet grouping and PDF cleanup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

VERB_PATTERN = re.compile(
    r"\b(State|Describe|Define|Calculate|Identify|Explain|Use|Draw|Write|Interpret|"
    r"Predict|Construct|Relate|Compare|Distinguish|Show|Determine|Deduce|Suggest|"
    r"Evaluate|Outline|List|Name|Give|Add|Remove|Measure|Record|Observe|Test|"
    r"Investigate|Classify|Select|Apply|Convert|Balance|Complete|Label|Analyse|Analyze)\b",
    re.I,
)

SUB_BULLET_RE = re.compile(r"^\(([a-z])\)\s*(.*)$", re.I | re.S)
TRAILING_PAGE_RE = re.compile(r"\s+\d{1,2}(?:\s+\d{1,2})?\s*$")
MERGED_OBJECTIVE_RE = re.compile(
    r"\s+\d{1,2}\s+(?=(?:Draw|Define|State|Calculate|Describe|Explain|Identify|Use|Write|"
    r"Predict|Construct|Relate|Compare|Determine|Suggest|Evaluate|Outline|Label|Analyse|Analyze|"
    r"Understand|Devise|Recognise|Recognize)\b)",
    re.I,
)

MAIN_TOPIC_NAMES = {
    "states of matter",
    "atoms, elements and compounds",
    "stoichiometry",
    "electrochemistry",
    "chemical energetics",
    "chemical reactions",
    "acids, bases and salts",
    "the periodic table",
    "metals",
    "chemistry of the environment",
    "organic chemistry",
    "experimental techniques and chemical analysis",
}

TYPE_BY_VERB: dict[str, str] = {
    "define": "CONCEPTUAL",
    "state": "CONCEPTUAL",
    "describe": "CONCEPTUAL",
    "explain": "CONCEPTUAL",
    "identify": "CONCEPTUAL",
    "relate": "CONCEPTUAL",
    "compare": "CONCEPTUAL",
    "distinguish": "CONCEPTUAL",
    "show": "CONCEPTUAL",
    "deduce": "CONCEPTUAL",
    "suggest": "CONCEPTUAL",
    "evaluate": "CONCEPTUAL",
    "outline": "CONCEPTUAL",
    "list": "CONCEPTUAL",
    "name": "LANGUAGE",
    "calculate": "PROCEDURAL",
    "determine": "PROCEDURAL",
    "predict": "PROCEDURAL",
    "construct": "PROCEDURAL",
    "balance": "PROCEDURAL",
    "convert": "PROCEDURAL",
    "understand": "CONCEPTUAL",
    "devise": "PROCEDURAL",
    "recognise": "CONCEPTUAL",
    "recognize": "CONCEPTUAL",
    "use": "PROCEDURAL",
    "measure": "PROCEDURAL",
    "record": "PROCEDURAL",
    "investigate": "PROCEDURAL",
    "test": "PROCEDURAL",
    "draw": "REPRESENTATIONAL",
    "write": "REPRESENTATIONAL",
    "interpret": "REPRESENTATIONAL",
    "label": "REPRESENTATIONAL",
    "complete": "REPRESENTATIONAL",
}


@dataclass
class MicroSkill:
    id: str
    code: str
    type: str
    subject: str
    domain: str
    subtopic: str
    subtopic_code: str
    main_topic_number: int
    name: str
    description: str
    evidence: list[str]
    assessment_prompt: str
    standards: list[str]
    color: str
    order: int = 0


def clean_text(text: str) -> str:
    text = text.replace("\x07", " ").replace("\ufffd", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = TRAILING_PAGE_RE.sub("", text).strip()
    return text


def infer_type(text: str) -> str:
    lower = text.lower().lstrip()
    for verb, skill_type in TYPE_BY_VERB.items():
        if lower.startswith(verb + " "):
            return skill_type
    return "CONCEPTUAL"


def make_name(text: str) -> str:
    text = clean_text(text)
    sub = SUB_BULLET_RE.match(text)
    if sub:
        text = sub.group(2).strip()
    if len(text) <= 72:
        return text[0].upper() + text[1:] if text else text
    cut = text[:69].rsplit(" ", 1)[0]
    return cut + "…"


def make_evidence(name: str, text: str, level: str = "O Level", spec: str = "5070") -> list[str]:
    base = name.rstrip("…")
    return [
        f"Demonstrates understanding: {base}",
        f"Can apply this skill in a {level} {spec} exam-style question",
    ]


def make_assessment_prompt(name: str) -> str:
    base = name.rstrip("…").lower()
    if base.startswith(("can ", "the ")):
        return f"Can the student {base}?"
    return f"Can the student demonstrate: {base}?"


def is_parent_stem(text: str) -> bool:
    text = clean_text(text)
    if text.endswith(":"):
        return True
    if SUB_BULLET_RE.match(text):
        return False
    if text.lower().endswith(" to include:"):
        return True
    if text.lower().endswith(" to calculate:"):
        return True
    if text.lower().endswith(" limited to:"):
        return True
    return False


def is_sub_bullet(text: str) -> bool:
    return bool(SUB_BULLET_RE.match(clean_text(text)))


def is_garbage_objective(text: str) -> bool:
    text = clean_text(text)
    if not text:
        return True
    if norm_title(text) in MAIN_TOPIC_NAMES:
        return True
    sub = SUB_BULLET_RE.match(text)
    if sub and len(sub.group(2).strip()) < 3:
        return True
    if re.fullmatch(r"\([a-z]\)", text, re.I):
        return True
    if len(text) < 8 and not is_sub_bullet(text):
        return True
    return False


def norm_title(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().strip())


def split_merged_objectives(text: str) -> list[str]:
    text = clean_text(text)
    parts = MERGED_OBJECTIVE_RE.split(text)
    return [clean_text(p) for p in parts if clean_text(p)]


def slug_id(code: str) -> str:
    safe = code.replace(".", "_").replace("#", "_")
    return f"ms_{safe}"


def group_objectives_by_subtopic(objectives: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for obj in objectives:
        grouped.setdefault(obj["subtopicCode"], []).append(obj)
    for code in grouped:
        grouped[code].sort(key=lambda o: o["ordinal"])
    return grouped


def process_subtopic_objectives(
    objectives: list[dict],
    subtopic_meta: dict,
    color: str,
    start_order: int,
    *,
    subject: str = "Chemistry",
    spec_slug: str = "5070",
    level: str = "O Level",
) -> list[MicroSkill]:
    skills: list[MicroSkill] = []
    order = start_order
    i = 0
    pending_stem: str | None = None
    pending_standards: list[str] = []

    while i < len(objectives):
        raw = objectives[i]
        text = clean_text(raw["text"])

        if is_garbage_objective(text):
            i += 1
            continue

        # Parent stem followed by sub-bullets
        if is_parent_stem(text) and not is_sub_bullet(text):
            pending_stem = text.rstrip(":").strip()
            pending_standards = [f"{spec_slug}:{raw['code']}"]
            i += 1
            while i < len(objectives) and is_sub_bullet(clean_text(objectives[i]["text"])):
                child = objectives[i]
                child_text = clean_text(child["text"])
                sub = SUB_BULLET_RE.match(child_text)
                child_body = sub.group(2).strip() if sub else child_text
                if len(child_body) < 3:
                    i += 1
                    continue
                full_desc = f"{pending_stem}: {child_body}"
                name = make_name(child_body if child_body else child_text)
                code = child["code"]
                skills.append(
                    MicroSkill(
                        id=slug_id(code),
                        code=code,
                        type=infer_type(pending_stem),
                        subject=subject,
                        domain=subtopic_meta["mainTopicName"],
                        subtopic=f"{subtopic_meta['code']} {subtopic_meta['title']}",
                        subtopic_code=subtopic_meta["code"],
                        main_topic_number=subtopic_meta["mainTopicNumber"],
                        name=name,
                        description=full_desc,
                        evidence=make_evidence(name, full_desc, level, spec_slug),
                        assessment_prompt=make_assessment_prompt(name),
                        standards=pending_standards + [f"{spec_slug}:{child['code']}"],
                        color=color,
                        order=order,
                    )
                )
                order += 1
                i += 1
            pending_stem = None
            pending_standards = []
            continue

        # Orphan sub-bullet — attach to previous skill's stem if possible
        if is_sub_bullet(text):
            sub = SUB_BULLET_RE.match(text)
            child_body = sub.group(2).strip() if sub else text
            if len(child_body) < 3:
                i += 1
                continue
            stem = pending_stem or (skills[-1].description if skills else subtopic_meta["title"])
            full_desc = f"{stem}: {child_body}" if child_body else text
            name = make_name(child_body or text)
            code = raw["code"]
            skills.append(
                MicroSkill(
                    id=slug_id(code),
                    code=code,
                    type=infer_type(text),
                    subject=subject,
                    domain=subtopic_meta["mainTopicName"],
                    subtopic=f"{subtopic_meta['code']} {subtopic_meta['title']}",
                    subtopic_code=subtopic_meta["code"],
                    main_topic_number=subtopic_meta["mainTopicNumber"],
                    name=name,
                    description=full_desc,
                    evidence=make_evidence(name, full_desc, level, spec_slug),
                    assessment_prompt=make_assessment_prompt(name),
                    standards=[f"{spec_slug}:{raw['code']}"],
                    color=color,
                    order=order,
                )
            )
            order += 1
            i += 1
            continue

        # Merge continuation line split across two objectives (e.g. "State that X and" + "explain Y")
        if (
            skills
            and not VERB_PATTERN.match(text)
            and skills[-1].subtopic_code == subtopic_meta["code"]
            and skills[-1].description.lower().endswith(" and")
        ):
            prev = skills[-1]
            merged_desc = prev.description + " " + text
            merged_name = make_name(merged_desc)
            prev.name = merged_name
            prev.description = merged_desc
            prev.evidence = make_evidence(merged_name, merged_desc, level, spec_slug)
            prev.assessment_prompt = make_assessment_prompt(merged_name)
            prev.standards.append(f"{spec_slug}:{raw['code']}")
            i += 1
            continue

        # Standalone objective — may contain merged PDF objectives
        parts = split_merged_objectives(text)
        for j, part in enumerate(parts):
            if is_garbage_objective(part):
                continue
            if is_parent_stem(part):
                pending_stem = part.rstrip(":").strip()
                pending_standards = [f"{spec_slug}:{raw['code']}"]
                break
            code = raw["code"] if len(parts) == 1 else f"{raw['code']}#{j + 1}"
            name = make_name(part)
            if not name or len(name) < 5:
                continue
            skills.append(
                MicroSkill(
                    id=slug_id(code),
                    code=code,
                    type=infer_type(part),
                    subject=subject,
                    domain=subtopic_meta["mainTopicName"],
                    subtopic=f"{subtopic_meta['code']} {subtopic_meta['title']}",
                    subtopic_code=subtopic_meta["code"],
                    main_topic_number=subtopic_meta["mainTopicNumber"],
                    name=name,
                    description=part,
                    evidence=make_evidence(name, part, level, spec_slug),
                    assessment_prompt=make_assessment_prompt(name),
                    standards=[f"{spec_slug}:{raw['code']}"],
                    color=color,
                    order=order,
                )
            )
            order += 1
        i += 1

    return [s for s in skills if s.name and len(s.name.strip()) >= 5]


def build_microskills(
    syllabus: dict,
    topic_colors: dict[int, str],
    *,
    subject: str = "Chemistry",
    spec_slug: str = "5070",
    level: str = "O Level",
) -> list[MicroSkill]:
    grouped = group_objectives_by_subtopic(syllabus["objectives"])

    all_skills: list[MicroSkill] = []
    order = 0

    for sub in syllabus["subtopics"]:
        code = sub["code"]
        objs = grouped.get(code, [])
        color = topic_colors.get(sub["mainTopicNumber"], "#B0BEC5")
        skills = process_subtopic_objectives(
            objs, sub, color, order,
            subject=subject, spec_slug=spec_slug, level=level,
        )
        all_skills.extend(skills)
        order += len(skills)

    return all_skills


def microskills_to_topics(skills: list[MicroSkill]) -> list[dict]:
    return [
        {
            "id": s.id,
            "code": s.code,
            "type": s.type,
            "subject": s.subject,
            "domain": s.domain,
            "subtopic": s.subtopic,
            "subtopicCode": s.subtopic_code,
            "mainTopicNumber": s.main_topic_number,
            "name": s.name,
            "description": s.description,
            "evidence": s.evidence,
            "assessmentPrompt": s.assessment_prompt,
            "standards": s.standards,
            "color": s.color,
            "order": s.order,
            "ageRangeStart": 14,
            "ageRangeEnd": 16,
        }
        for s in skills
    ]
