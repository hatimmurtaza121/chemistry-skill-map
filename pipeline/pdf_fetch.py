"""Download syllabus PDFs from HTTPS URLs."""

from __future__ import annotations

import ipaddress
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

MAX_PDF_BYTES = 50 * 1024 * 1024
DOWNLOAD_TIMEOUT_SEC = 60
USER_AGENT = "map-syllabus-fetch/1.0"


def _hostname_blocked(host: str) -> bool:
    host = host.lower().rstrip(".")
    if host in {"localhost", "0.0.0.0"}:
        return True
    if host.endswith(".local") or host.endswith(".internal"):
        return True
    try:
        addr = ipaddress.ip_address(host)
        return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved
    except ValueError:
        return False


def validate_pdf_url(url: str) -> str:
    url = url.strip()
    if not url:
        raise ValueError("PDF URL is required")
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("PDF URL must use https://")
    host = parsed.hostname
    if not host or _hostname_blocked(host):
        raise ValueError("PDF URL host is not allowed")
    if not parsed.path.lower().endswith(".pdf"):
        raise ValueError("URL should point to a .pdf file")
    return url


def _filename_from_url(url: str) -> str:
    name = Path(urlparse(url).path).name
    if name.lower().endswith(".pdf") and name != ".pdf":
        return name
    return "syllabus.pdf"


def fetch_pdf_from_url(url: str, *, max_bytes: int = MAX_PDF_BYTES) -> tuple[bytes, str]:
    url = validate_pdf_url(url)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=DOWNLOAD_TIMEOUT_SEC) as response:
        content_type = (response.headers.get("Content-Type") or "").lower()
        if content_type and "pdf" not in content_type and "octet-stream" not in content_type:
            raise ValueError(f"URL did not return a PDF (Content-Type: {content_type})")

        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = response.read(1024 * 64)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"PDF too large (max {max_bytes // (1024 * 1024)} MB)")
            chunks.append(chunk)

    pdf_bytes = b"".join(chunks)
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("Downloaded file is not a valid PDF")
    return pdf_bytes, _filename_from_url(url)
