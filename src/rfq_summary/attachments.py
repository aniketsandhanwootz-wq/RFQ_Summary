from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from typing import List, Tuple, Optional
from urllib.parse import urlparse

import httpx

from .config import Settings
from .schema import AttachmentFinding
from .parsers.pdf import analyze_pdf_bytes
from .parsers.excel import analyze_excel_bytes
from .parsers.image import analyze_image_bytes


def _clean_url(u: str) -> str:
    s = (u or "").strip()
    if not s:
        return ""
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()
    s = s.replace("\n", "").replace("\r", "").strip()
    while s and s[-1] in (")", "]", "}", ","):
        s = s[:-1].rstrip()
    if " " in s:
        s = s.replace(" ", "%20")
    return s


def _is_probably_ms_folder_link(url: str) -> bool:
    u = (url or "").lower()
    if ":f:" in u:
        return True
    return ("sharepoint.com" in u or "onedrive.live.com" in u) and ("?e=" in u or "cid=" in u) and ("folder" in u)


def _guess_kind(url: str, content_type: str | None) -> str:
    u = (url or "").lower()
    ct = (content_type or "").lower()

    if _is_probably_ms_folder_link(u):
        return "folder"
    if u.endswith(".pdf") or ct.startswith("application/pdf"):
        return "pdf"
    if u.endswith(".xlsx") or u.endswith(".xlsm") or "spreadsheet" in ct:
        return "excel"
    if any(u.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif"]) or ct.startswith("image/"):
        return "image"
    return "unknown"


def _safe_filename_from_url(url: str) -> str:
    try:
        p = urlparse(url)
        name = (p.path.rsplit("/", 1)[-1] or "file").strip()
        return name[:120] or "file"
    except Exception:
        return "file"


@dataclass(frozen=True)
class HttpFetcher:
    settings: Settings

    def fetch(self, url: str) -> Tuple[bytes, Optional[str]]:
        max_bytes = int(self.settings.max_attachment_bytes)

        headers = {"User-Agent": "rfq-summary-bot/1.0", "Accept": "*/*"}
        timeout = httpx.Timeout(connect=15.0, read=45.0, write=15.0, pool=15.0)

        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            content_type = None

            # HEAD best effort (some hosts block HEAD; ignore failures)
            try:
                h = client.head(url)
                if h.status_code < 400:
                    content_type = h.headers.get("content-type")
                    cl = h.headers.get("content-length")
                    if cl and cl.isdigit() and int(cl) > max_bytes:
                        raise ValueError(f"Attachment too large (content-length={cl} > {max_bytes})")
            except Exception:
                pass

            r = client.get(url)
            r.raise_for_status()

            content_type = r.headers.get("content-type") or content_type
            data = r.content
            if len(data) > max_bytes:
                raise ValueError(f"Attachment too large (bytes={len(data)} > {max_bytes})")

        return data, content_type


def analyze_attachments(settings: Settings, urls: List[str]) -> List[AttachmentFinding]:
    out: List[AttachmentFinding] = []
    fetcher = HttpFetcher(settings)

    for url in urls:
        u = _clean_url(url or "")
        if not u:
            continue

        if _is_probably_ms_folder_link(u):
            out.append(
                AttachmentFinding(
                    url=u,
                    kind="folder",
                    summary=(
                        "Folder link detected (SharePoint/OneDrive). "
                        "Deep traversal requires Microsoft Graph integration."
                    ),
                    data={"filename": _safe_filename_from_url(u), "action": "graph_required"},
                )
            )
            continue

        try:
            data, ctype = fetcher.fetch(u)
            kind = _guess_kind(u, ctype)
            fname = _safe_filename_from_url(u)

            if kind == "pdf":
                finding = analyze_pdf_bytes(settings, u, data)
            elif kind == "excel":
                finding = analyze_excel_bytes(settings, u, data)
            elif kind == "image":
                finding = analyze_image_bytes(settings, u, data)
            else:
                mt, _ = mimetypes.guess_type(u)
                finding = AttachmentFinding(
                    url=u,
                    kind="unknown",
                    summary=f"Downloaded '{fname}'. Unsupported type (content-type={ctype or mt or 'unknown'}).",
                    data={"filename": fname, "content_type": ctype or mt or ""},
                )

            out.append(finding)

        except Exception as e:
            out.append(
                AttachmentFinding(
                    url=u,
                    kind="unknown",
                    summary=f"Failed to analyze attachment: {type(e).__name__}: {e}",
                    data={"filename": _safe_filename_from_url(u)},
                )
            )

    return out