#!/usr/bin/env python3
"""
build.py — Build Marble-style micro-skill graph JSON from syllabus data.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(PIPELINE_DIR))

from microskills import build_microskills, microskills_to_topics
from map_utils import upsert_map_in_catalog

ROOT = Path(__file__).resolve().parent.parent
PIPELINE = Path(__file__).resolve().parent
INTERMEDIATE = PIPELINE / "intermediate"
DATA = ROOT / "data"
VIZ_DATA = ROOT / "viz" / "data"
MAP_ID = "chemistry-5070"
MAP_DATA = DATA / "maps" / MAP_ID
VIZ_MAP_DATA = VIZ_DATA / "maps" / MAP_ID
RULES_PATH = PIPELINE / "dependency_rules.json"

TOPIC_COLORS = {
    1: "#4FC3F7",
    2: "#81C784",
    3: "#FFB74D",
    4: "#E57373",
    5: "#BA68C8",
    6: "#FFD54F",
    7: "#4DB6AC",
    8: "#FF8A65",
    9: "#A1887F",
    10: "#90A4AE",
    11: "#F06292",
    12: "#7986CB",
}


def load_syllabus() -> dict:
    path = INTERMEDIATE / "syllabus.json"
    if not path.exists():
        raise FileNotFoundError(f"Run extract.py first. Missing {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def build_standards(syllabus: dict) -> dict:
    topics = []
    for obj in syllabus["objectives"]:
        topics.append({
            "key": f"5070:{obj['code']}",
            "code": obj["code"],
            "subtopicCode": obj["subtopicCode"],
            "text": obj["text"],
        })
    return {
        "curriculumCount": 1,
        "curricula": [{
            "slug": "5070",
            "name": "Cambridge O Level Chemistry",
            "version": "2026-2028",
            "textIncluded": True,
            "topicCount": len(topics),
            "topics": topics,
        }],
    }


def build_micro_dependencies(
    skills: list[dict],
    syllabus: dict,
    spec: str = "",
) -> list[dict]:
    edges: list[dict] = []
    seen: set[tuple[str, str]] = set()

    by_subtopic: dict[str, list[str]] = defaultdict(list)
    for s in skills:
        by_subtopic[s["subtopicCode"]].append(s["id"])

    first_of_sub = {code: ids[0] for code, ids in by_subtopic.items() if ids}
    last_of_sub = {code: ids[-1] for code, ids in by_subtopic.items() if ids}

    def add_edge(prereq_id: str, topic_id: str, strength: str, reason: str):
        if prereq_id == topic_id:
            return
        key = (topic_id, prereq_id)
        if key in seen:
            return
        seen.add(key)
        edges.append({
            "topicId": topic_id,
            "prerequisiteId": prereq_id,
            "strength": strength,
            "reason": reason,
        })

    for ids in by_subtopic.values():
        for i in range(1, len(ids)):
            add_edge(
                ids[i - 1],
                ids[i],
                "soft",
                "Sequential skill progression within subtopic",
            )

    if spec == "5070" and RULES_PATH.exists():
        rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        for rule in rules.get("edges", []):
            src_last = last_of_sub.get(rule["from"])
            dst_first = first_of_sub.get(rule["to"])
            if src_last and dst_first:
                add_edge(
                    src_last,
                    dst_first,
                    rule["strength"],
                    rule["reason"],
                )

    return edges


def detect_cycles(edges: list[dict]) -> bool:
    adj: dict[str, list[str]] = defaultdict(list)
    nodes: set[str] = set()
    for e in edges:
        adj[e["topicId"]].append(e["prerequisiteId"])
        nodes.add(e["topicId"])
        nodes.add(e["prerequisiteId"])

    visiting: set[str] = set()
    visited: set[str] = set()

    def dfs(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for nxt in adj.get(node, []):
            if dfs(nxt):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(dfs(n) for n in nodes)


def resolve_cycles(edges: list[dict]) -> list[dict]:
    result = list(edges)
    if not detect_cycles(result):
        return result
    print("Warning: cycle detected — removing soft sequential edges")
    result = [e for e in result if e["strength"] == "hard" or "Sequential" not in e["reason"]]
    if detect_cycles(result):
        print("Warning: still cyclic — keeping hard edges only")
        result = [e for e in result if e["strength"] == "hard"]
    return result


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, obj: dict | list) -> bytes:
    text = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path.read_bytes()


def main() -> int:
    syllabus = load_syllabus()
    micro_list = build_microskills(syllabus, TOPIC_COLORS)
    topics = microskills_to_topics(micro_list)
    dependencies = resolve_cycles(build_micro_dependencies(topics, syllabus, spec="5070"))
    standards = build_standards(syllabus)

    has_prereq = {d["topicId"] for d in dependencies}
    for t in topics:
        t["isRoot"] = t["id"] not in has_prereq
        t["entryPoint"] = t["code"] == "1.1.1"

    topics_doc = {"topicCount": len(topics), "granularity": "microskills", "topics": topics}
    deps_doc = {"edgeCount": len(dependencies), "dependencies": dependencies}

    file_hashes: dict[str, dict] = {}
    for name, doc in {
        "topics.json": topics_doc,
        "dependencies.json": deps_doc,
        "curriculum-standards.json": standards,
    }.items():
        raw = write_json(MAP_DATA / name, doc)
        write_json(VIZ_MAP_DATA / name, doc)
        write_json(DATA / name, doc)
        write_json(VIZ_DATA / name, doc)
        file_hashes[name] = {"bytes": len(raw), "sha256": sha256_bytes(raw)}

    subtopics = len(syllabus["subtopics"])
    manifest = {
        "mapId": MAP_ID,
        "dataset": "O Level Chemistry Skill Graph",
        "taxonomyVersion": "v2-microskills",
        "granularity": "microskills",
        "spec": "5070",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": syllabus.get("source", "unknown.pdf"),
        "counts": {
            "microskills": len(topics),
            "subtopics": subtopics,
            "dependencies": len(dependencies),
            "objectives": len(syllabus["objectives"]),
            "mainTopics": len(syllabus["mainTopics"]),
            "entryPoint": "1.1.1",
        },
        "files": file_hashes,
    }

    catalog_entry = {
        "id": MAP_ID,
        "name": "O Level Chemistry",
        "spec": "5070",
        "subject": "Chemistry",
        "level": "O Level",
        "available": True,
        "description": "Cambridge syllabus 2026–2028",
        "dataPath": f"maps/{MAP_ID}",
    }
    upsert_map_in_catalog(catalog_entry)

    for dest in (MAP_DATA, VIZ_MAP_DATA, DATA, VIZ_DATA):
        write_json(dest / "manifest.json", manifest)

    print("Built micro-skill graph:")
    print(f"  {len(topics)} micro-skills (from {len(syllabus['objectives'])} objectives, {subtopics} subtopics)")
    print(f"  {len(dependencies)} dependency edges")
    print(f"  -> {MAP_DATA}/")
    print(f"  -> {VIZ_MAP_DATA}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
