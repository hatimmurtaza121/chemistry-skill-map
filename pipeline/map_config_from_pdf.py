"""Build map configuration from PDF metadata with optional user overrides."""

from __future__ import annotations

from pathlib import Path

from map_utils import MapConfig, slugify_map_id, unique_map_id
from pdf_metadata import detect_pdf_metadata


def _finish_display_name(name: str, meta: dict) -> str:
    """Ensure map name ends with syllabus form, level, and optional year range."""
    name = name.strip()
    if not name:
        return meta["displayName"]

    level_label = f"{meta['syllabusForm']} {meta['level']}".strip()
    year_range = meta.get("yearRange")

    has_form = meta["syllabusForm"].lower() in name.lower()
    has_level = meta["level"].lower() in name.lower()
    has_years = not year_range or f"({year_range})" in name

    if has_form and has_level and has_years:
        return name

    result = name
    if not (has_form and has_level):
        result = f"{name} — {level_label}"
    if year_range and f"({year_range})" not in result:
        result += f" ({year_range})"
    return result


def resolve_map_config(
    pdf_path: Path,
    *,
    name: str = "",
    spec: str = "",
    subject: str = "",
    level: str = "",
    description: str = "",
    pdf_name: str = "",
) -> MapConfig:
    meta = detect_pdf_metadata(pdf_path, pdf_name=pdf_name or pdf_path.name)

    resolved_spec = spec.strip() or meta["spec"]
    resolved_subject = subject.strip() or meta["subject"]
    resolved_level = level.strip() or meta["level"]
    resolved_description = description.strip() or meta["description"]

    if name.strip():
        resolved_name = _finish_display_name(name, meta)
    else:
        resolved_name = meta["displayName"]

    map_id = unique_map_id(slugify_map_id(resolved_name, resolved_spec))

    return MapConfig(
        map_id=map_id,
        name=resolved_name,
        spec=resolved_spec,
        subject=resolved_subject,
        level=resolved_level,
        description=resolved_description,
        pdf_name=pdf_name or pdf_path.name,
    )
