"""Shared helpers for multi-map generation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
VIZ_DATA = ROOT / "viz" / "data"

PALETTE = [
    "#4FC3F7", "#81C784", "#FFB74D", "#E57373", "#BA68C8", "#FFD54F",
    "#4DB6AC", "#FF8A65", "#A1887F", "#90A4AE", "#F06292", "#7986CB",
    "#64B5F6", "#AED581", "#FFF176", "#CE93D8", "#80CBC4", "#FFAB91",
]


@dataclass
class MapConfig:
    map_id: str
    name: str
    spec: str
    subject: str
    level: str
    description: str = ""
    pdf_name: str = ""

    @property
    def data_path(self) -> str:
        return f"maps/{self.map_id}"

    def topic_colors(self, main_topic_count: int) -> dict[int, str]:
        return {n: PALETTE[(n - 1) % len(PALETTE)] for n in range(1, main_topic_count + 1)}


def slugify_map_id(name: str, spec: str) -> str:
    raw = f"{name}-{spec}".lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return slug[:56] or "custom-map"


def unique_map_id(base: str) -> str:
    catalog = load_catalog()
    existing = {m["id"] for m in catalog.get("maps", [])}
    if base not in existing:
        return base
    n = 2
    while f"{base}-{n}" in existing:
        n += 1
    return f"{base}-{n}"


def load_catalog() -> dict:
    path = DATA / "maps.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"defaultMap": "", "maps": []}


def save_catalog(catalog: dict) -> None:
    text = json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"
    for dest in (DATA, VIZ_DATA):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "maps.json").write_text(text, encoding="utf-8")


def upsert_map_in_catalog(entry: dict, make_default: bool = False) -> None:
    catalog = load_catalog()
    by_id = {m["id"]: m for m in catalog.get("maps", [])}
    by_id[entry["id"]] = entry
    catalog["maps"] = sorted(by_id.values(), key=lambda m: m.get("name", m["id"]))
    if not catalog.get("defaultMap") or make_default:
        catalog["defaultMap"] = entry["id"]
    save_catalog(catalog)
