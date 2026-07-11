#!/usr/bin/env python3
"""Generate a skill map from an uploaded Cambridge-style syllabus PDF."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PIPELINE_DIR))

from build import build_micro_dependencies, detect_cycles, resolve_cycles
from extract import extract_syllabus_from_pdf
from map_config_from_pdf import resolve_map_config
from map_utils import DATA, VIZ_DATA, MapConfig, upsert_map_in_catalog
from microskills import build_microskills, microskills_to_topics

ROOT = Path(__file__).resolve().parent.parent
RULES_PATH = PIPELINE_DIR / "dependency_rules.json"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, obj: dict | list) -> bytes:
    text = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path.read_bytes()


def build_standards(syllabus: dict, config: MapConfig) -> dict:
    topics = []
    for obj in syllabus["objectives"]:
        topics.append({
            "key": f"{config.spec}:{obj['code']}",
            "code": obj["code"],
            "subtopicCode": obj["subtopicCode"],
            "text": obj["text"],
        })
    return {
        "curriculumCount": 1,
        "curricula": [{
            "slug": config.spec,
            "name": config.name,
            "version": syllabus.get("source", "uploaded"),
            "textIncluded": True,
            "topicCount": len(topics),
            "topics": topics,
        }],
    }


def build_dependencies(skills: list[dict], syllabus: dict, config: MapConfig) -> list[dict]:
    edges = build_micro_dependencies(skills, syllabus, spec=config.spec)
    if config.spec == "5070" and RULES_PATH.exists():
        return resolve_cycles(edges)
    if detect_cycles(edges):
        return resolve_cycles(edges)
    return edges


def pick_entry_point(topics: list[dict], has_prereq: set[str]) -> str | None:
    for code in ("1.1.1", "1.1"):
        match = next((t for t in topics if t["code"] == code), None)
        if match:
            return match["code"]
    roots = [t for t in topics if t["id"] not in has_prereq]
    return roots[0]["code"] if roots else (topics[0]["code"] if topics else None)


def generate_map(pdf_path: Path, config: MapConfig) -> dict:
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    syllabus = extract_syllabus_from_pdf(pdf_path, spec=config.spec)
    if not syllabus["objectives"]:
        raise ValueError(
            "No learning objectives found in PDF. "
            "Use a Cambridge-style syllabus with numbered subtopics (e.g. 1.1 Title) "
            "and verb-led objectives (State, Describe, Calculate…)."
        )

    main_count = max((t["mainTopicNumber"] for t in syllabus["subtopics"]), default=1)
    colors = config.topic_colors(main_count)
    micro_list = build_microskills(
        syllabus,
        colors,
        subject=config.subject,
        spec_slug=config.spec,
        level=config.level,
    )
    topics = microskills_to_topics(micro_list)
    if not topics:
        raise ValueError("Could not build micro-skills from extracted objectives.")

    dependencies = build_dependencies(topics, syllabus, config)
    standards = build_standards(syllabus, config)

    has_prereq = {d["topicId"] for d in dependencies}
    entry_code = pick_entry_point(topics, has_prereq)
    for t in topics:
        t["isRoot"] = t["id"] not in has_prereq
        t["entryPoint"] = entry_code is not None and t["code"] == entry_code

    map_data = DATA / "maps" / config.map_id
    viz_map_data = VIZ_DATA / "maps" / config.map_id

    topics_doc = {"topicCount": len(topics), "granularity": "microskills", "topics": topics}
    deps_doc = {"edgeCount": len(dependencies), "dependencies": dependencies}

    file_hashes: dict[str, dict] = {}
    for name, doc in {
        "topics.json": topics_doc,
        "dependencies.json": deps_doc,
        "curriculum-standards.json": standards,
    }.items():
        raw = write_json(map_data / name, doc)
        write_json(viz_map_data / name, doc)
        file_hashes[name] = {"bytes": len(raw), "sha256": sha256_bytes(raw)}

    manifest = {
        "mapId": config.map_id,
        "dataset": f"{config.name} Skill Graph",
        "taxonomyVersion": "v2-microskills",
        "granularity": "microskills",
        "spec": config.spec,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": syllabus.get("source", config.pdf_name),
        "counts": {
            "microskills": len(topics),
            "subtopics": len(syllabus["subtopics"]),
            "dependencies": len(dependencies),
            "objectives": len(syllabus["objectives"]),
            "mainTopics": len(syllabus["mainTopics"]),
            "entryPoint": entry_code,
        },
        "files": file_hashes,
    }
    for dest in (map_data, viz_map_data):
        write_json(dest / "manifest.json", manifest)

    catalog_entry = {
        "id": config.map_id,
        "name": config.name,
        "spec": config.spec,
        "subject": config.subject,
        "level": config.level,
        "available": True,
        "description": config.description or f"Generated from {config.pdf_name}",
        "dataPath": config.data_path,
    }
    upsert_map_in_catalog(catalog_entry)

    return {"mapId": config.map_id, "manifest": manifest, "catalogEntry": catalog_entry}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate skill map from syllabus PDF")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf")
    source.add_argument("--url", help="HTTPS URL to a syllabus PDF")
    parser.add_argument("--name", default="")
    parser.add_argument("--spec", default="")
    parser.add_argument("--subject", default="")
    parser.add_argument("--level", default="")
    parser.add_argument("--description", default="")
    args = parser.parse_args()

    if args.pdf:
        pdf_path = Path(args.pdf)
        pdf_name = pdf_path.name
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
    else:
        from pdf_fetch import fetch_pdf_from_url

        pdf_bytes, pdf_name = fetch_pdf_from_url(args.url)
        UPLOADS = ROOT / "sources" / "uploads"
        UPLOADS.mkdir(parents=True, exist_ok=True)
        pdf_path = UPLOADS / f"_cli_{pdf_name}"
        pdf_path.write_bytes(pdf_bytes)

    config = resolve_map_config(
        pdf_path,
        name=args.name,
        spec=args.spec,
        subject=args.subject,
        level=args.level,
        description=args.description,
        pdf_name=pdf_name,
    )

    final_pdf = ROOT / "sources" / "uploads" / f"{config.map_id}.pdf"
    final_pdf.parent.mkdir(parents=True, exist_ok=True)
    if pdf_path != final_pdf:
        if final_pdf.exists():
            final_pdf.unlink()
        pdf_path.replace(final_pdf)
        pdf_path = final_pdf

    result = generate_map(pdf_path, config)
    print(json.dumps({
        "ok": True,
        "mapId": result["mapId"],
        "name": config.name,
        "counts": result["manifest"]["counts"],
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        sys.exit(1)
