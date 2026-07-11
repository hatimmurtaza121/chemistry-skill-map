#!/usr/bin/env python3
"""Smoke-test map generation API flows without manual browser testing."""

from __future__ import annotations

import json
import mimetypes
import sys
import uuid
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
API = f"http://127.0.0.1:{__import__('os').environ.get('PORT', '8081')}/api/maps/generate"
PDF_5070 = ROOT / "sources" / "5070-2026-2028.pdf"
PDF_URL = "https://www.cambridgeinternational.org/Images/664563-2025-2027-syllabus.pdf"


def multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes]] | None = None) -> tuple[bytes, str]:
    boundary = f"----maptest{uuid.uuid4().hex}"
    body = BytesIO()
    for name, value in fields.items():
        body.write(f"--{boundary}\r\n".encode())
        body.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.write(value.encode("utf-8"))
        body.write(b"\r\n")
    for name, (filename, data) in (files or {}).items():
        body.write(f"--{boundary}\r\n".encode())
        body.write(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
        )
        body.write(b"Content-Type: application/pdf\r\n\r\n")
        body.write(data)
        body.write(b"\r\n")
    body.write(f"--{boundary}--\r\n".encode())
    return body.getvalue(), boundary


def post_map(payload: bytes, boundary: str) -> dict:
    req = Request(
        API,
        data=payload,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urlopen(req, timeout=180) as res:
        return json.loads(res.read().decode("utf-8"))


def cleanup_map(map_id: str) -> None:
    for base in (ROOT / "data", ROOT / "viz" / "data"):
        catalog_path = base / "maps.json"
        if catalog_path.exists():
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            catalog["maps"] = [m for m in catalog["maps"] if m["id"] != map_id]
            catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        map_dir = base / "maps" / map_id
        if map_dir.exists():
            import shutil
            shutil.rmtree(map_dir)
    pdf = ROOT / "sources" / "uploads" / f"{map_id}.pdf"
    if pdf.exists():
        pdf.unlink()


def main() -> int:
    if not PDF_5070.exists():
        print("SKIP file upload test: sources/5070-2026-2028.pdf missing")
        return 1

    created: list[str] = []
    try:
        print("1) File upload flow…")
        body, boundary = multipart({}, {"pdf": (PDF_5070.name, PDF_5070.read_bytes())})
        data = post_map(body, boundary)
        assert data["ok"], data
        assert data["name"].startswith("Chemistry 5070"), data["name"]
        assert data["counts"]["microskills"] > 100, data["counts"]
        created.append(data["mapId"])
        print("   OK", data["mapId"], data["name"], data["counts"])

        print("2) PDF URL flow…")
        body, boundary = multipart({"pdfUrl": PDF_URL})
        data = post_map(body, boundary)
        assert data["ok"], data
        assert "9701" in data["name"], data["name"]
        assert data["counts"]["microskills"] > 50, data["counts"]
        created.append(data["mapId"])
        print("   OK", data["mapId"], data["name"], data["counts"])

        print("3) Missing source…")
        body, boundary = multipart({})
        try:
            post_map(body, boundary)
            print("   FAIL expected 400")
            return 1
        except Exception as exc:
            if "400" not in str(exc):
                raise
            print("   OK rejected:", exc)

        print("All API smoke tests passed.")
        return 0
    finally:
        for map_id in created:
            cleanup_map(map_id)
            print("Cleaned up", map_id)


if __name__ == "__main__":
    sys.exit(main())
