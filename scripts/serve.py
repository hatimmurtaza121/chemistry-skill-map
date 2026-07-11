#!/usr/bin/env python3
"""Serve the project and expose map-generation API."""

from __future__ import annotations

import json
import os
import re
import sys
import traceback
import uuid
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
VIZ = ROOT / "viz"
PIPELINE = ROOT / "pipeline"
UPLOADS = ROOT / "sources" / "uploads"
VIZ_DATA = ROOT / "viz" / "data"
DATA = ROOT / "data"
PORT = int(os.environ.get("PORT", "8080"))
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAP_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
EXPORT_FILES = (
    "manifest.json",
    "topics.json",
    "dependencies.json",
    "curriculum-standards.json",
)

sys.path.insert(0, str(PIPELINE))


def parse_multipart(body: bytes, content_type: str) -> tuple[dict[str, str], dict[str, tuple[str, bytes]]]:
    boundary = content_type.split("boundary=", 1)[1].strip().encode("latin-1")
    fields: dict[str, str] = {}
    files: dict[str, tuple[str, bytes]] = {}
    for block in body.split(b"--" + boundary):
        if b"Content-Disposition" not in block:
            continue
        header, _, content = block.partition(b"\r\n\r\n")
        header_text = header.decode("utf-8", errors="replace")
        name_m = re.search(r'name="([^"]+)"', header_text)
        file_m = re.search(r'filename="([^"]*)"', header_text)
        if not name_m:
            continue
        name = name_m.group(1)
        data = content.rstrip(b"\r\n--").rstrip(b"\r\n")
        if file_m and file_m.group(1):
            files[name] = (file_m.group(1), data)
        else:
            fields[name] = data.decode("utf-8", errors="replace").strip()
    return fields, files


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(VIZ), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json_response(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        export_match = re.match(r"^/api/maps/([^/]+)/export$", path)
        if export_match:
            self.handle_export_map(export_match.group(1))
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/maps/generate":
            self.handle_generate_map()
            return
        self.send_error(404, "Not found")

    def handle_generate_map(self) -> None:
        try:
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                self._json_response(400, {"ok": False, "error": "Expected multipart/form-data"})
                return

            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_UPLOAD_BYTES:
                self._json_response(400, {"ok": False, "error": "PDF too large (max 50 MB)"})
                return

            body = self.rfile.read(length)
            fields, files = parse_multipart(body, content_type)

            pdf_url = fields.get("pdfUrl", "").strip()
            pdf_bytes: bytes | None = None
            filename = "syllabus.pdf"

            if "pdf" in files:
                filename, pdf_bytes = files["pdf"]
                if not filename.lower().endswith(".pdf") or not pdf_bytes.startswith(b"%PDF"):
                    self._json_response(400, {"ok": False, "error": "Upload must be a PDF file"})
                    return
            elif pdf_url:
                from pdf_fetch import fetch_pdf_from_url

                try:
                    pdf_bytes, filename = fetch_pdf_from_url(pdf_url)
                except Exception as exc:
                    self._json_response(400, {"ok": False, "error": f"Could not download PDF: {exc}"})
                    return
            else:
                self._json_response(400, {"ok": False, "error": "Provide a PDF file or a PDF URL"})
                return

            name = fields.get("name", "").strip()
            spec = fields.get("spec", "").strip()
            subject = fields.get("subject", "").strip()
            level = fields.get("level", "").strip()
            description = fields.get("description", "").strip()

            from map_config_from_pdf import resolve_map_config
            from generate_map import generate_map

            UPLOADS.mkdir(parents=True, exist_ok=True)
            temp_path = UPLOADS / f"_upload_{uuid.uuid4().hex}.pdf"
            temp_path.write_bytes(pdf_bytes)

            config = resolve_map_config(
                temp_path,
                name=name,
                spec=spec,
                subject=subject,
                level=level,
                description=description,
                pdf_name=filename,
            )
            pdf_path = UPLOADS / f"{config.map_id}.pdf"
            if pdf_path != temp_path:
                if pdf_path.exists():
                    pdf_path.unlink()
                temp_path.rename(pdf_path)
            elif not pdf_path.exists():
                temp_path.write_bytes(pdf_bytes)

            result = generate_map(pdf_path, config)
            self._json_response(200, {
                "ok": True,
                "mapId": result["mapId"],
                "name": config.name,
                "counts": result["manifest"]["counts"],
                "viewUrl": f"/index.html?map={result['mapId']}",
            })
        except Exception as exc:
            traceback.print_exc()
            self._json_response(500, {"ok": False, "error": str(exc)})

    def handle_export_map(self, map_id: str) -> None:
        try:
            if not MAP_ID_RE.match(map_id):
                self._json_response(400, {"ok": False, "error": "Invalid map id"})
                return

            map_dir = VIZ_DATA / "maps" / map_id
            if not map_dir.is_dir():
                map_dir = DATA / "maps" / map_id
            if not map_dir.is_dir():
                self._json_response(404, {"ok": False, "error": f"Map not found: {map_id}"})
                return

            catalog_entry = None
            catalog_path = VIZ_DATA / "maps.json"
            if catalog_path.exists():
                catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
                catalog_entry = next(
                    (m for m in catalog.get("maps", []) if m.get("id") == map_id),
                    None,
                )

            readme = (
                f"Skill map export: {map_id}\n\n"
                "Files:\n"
                "  manifest.json — metadata and counts\n"
                "  topics.json — micro-skills (nodes)\n"
                "  dependencies.json — prerequisite edges\n"
                "  curriculum-standards.json — syllabus objectives\n"
                "  catalog-entry.json — map listing metadata\n\n"
                "Load topics.topics as nodes and dependencies.dependencies as edges.\n"
            )

            buffer = BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("README.txt", readme)
                for name in EXPORT_FILES:
                    file_path = map_dir / name
                    if file_path.exists():
                        zf.write(file_path, arcname=f"{map_id}/{name}")
                if catalog_entry:
                    zf.writestr(
                        f"{map_id}/catalog-entry.json",
                        json.dumps(catalog_entry, indent=2, ensure_ascii=False) + "\n",
                    )

            payload = buffer.getvalue()
            filename = f"{map_id}-skill-map.zip"
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(payload)))
            self._cors()
            self.end_headers()
            self.wfile.write(payload)
        except Exception as exc:
            traceback.print_exc()
            self._json_response(500, {"ok": False, "error": str(exc)})


def main() -> int:
    server = ThreadingHTTPServer(("", PORT), Handler)
    print(f"Serving {ROOT}")
    print(f"Open http://localhost:{PORT}/")
    print(f"Create maps at http://localhost:{PORT}/create.html")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
