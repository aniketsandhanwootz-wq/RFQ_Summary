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


def _is_probably_ms_folder_link(url: str) -> bool:
    """
    SharePoint/OneDrive folder share links commonly contain ':f:'.
    Example: https://...sharepoint.com/:f:/g/personal/... ?e=...
    """
    u = (url or "").lower()
    return ":f:" in u or ("sharepoint.com" in u and "folder" in u)


def _guess_kind(url: str, content_type: str | None) -> str:
    u = (url or "").lower()
    if _is_probably_ms_folder_link(u):
        return "folder"
    if u.endswith(".pdf") or (content_type or "").startswith("application/pdf"):
        return "pdf"
    if u.endswith(".xlsx") or u.endswith(".xlsm") or "spreadsheet" in (content_type or ""):
        return "excel"
    if any(u.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif"]) or (content_type or "").startswith("image/"):
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
        """
        Fetches bytes + returns content-type. Enforces MAX_ATTACHMENT_BYTES.
        """
        max_bytes = int(self.settings.max_attachment_bytes)

        with httpx.Client(timeout=60, follow_redirects=True) as client:
            # HEAD first (best effort)
            try:
                h = client.head(url)
                if h.status_code < 400:
                    cl = h.headers.get("content-length")
                    if cl and cl.isdigit() and int(cl) > max_bytes:
                        raise ValueError(f"Attachment too large (content-length={cl} > {max_bytes})")
            except Exception:
                pass  # continue with GET

            r = client.get(url)
            r.raise_for_status()

            content_type = r.headers.get("content-type")
            data = r.content
            if len(data) > max_bytes:
                raise ValueError(f"Attachment too large (bytes={len(data)} > {max_bytes})")

        return data, content_type


def analyze_attachments(settings: Settings, urls: List[str]) -> List[AttachmentFinding]:
    """
    Downloads + analyzes each attachment URL.
    Folder traversal is not implemented here (requires Microsoft Graph).
    """
    out: List[AttachmentFinding] = []
    fetcher = HttpFetcher(settings)

    for url in urls:
        u = (url or "").strip()
        if not u:
            continue

        # Folder link: return finding that requires Graph traversal
        if _is_probably_ms_folder_link(u):
            out.append(
                AttachmentFinding(
                    url=u,
                    kind="folder",
                    summary="Folder link detected (SharePoint/OneDrive). Deep traversal requires Microsoft Graph integration.",
                    data={"filename": _safe_filename_from_url(u)},
                )
            )
            continue

        # Fetch + analyze
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
                # attempt by mime guess
                mt, _ = mimetypes.guess_type(u)
                finding = AttachmentFinding(
                    url=u,
                    kind="unknown",
                    summary=f"Downloaded '{fname}'. Unsupported type for deep analysis (content-type={ctype or mt or 'unknown'}).",
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