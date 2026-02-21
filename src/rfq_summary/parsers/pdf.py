from __future__ import annotations

from typing import Dict, Any, List
import re

from ..config import Settings
from ..schema import AttachmentFinding

# PyMuPDF
import fitz  # type: ignore

from .image import _ocr_text_from_pil_image  # reuse OCR helper


def _clean_text(s: str) -> str:
    s = (s or "").replace("\x00", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def analyze_pdf_bytes(settings: Settings, url: str, data: bytes) -> AttachmentFinding:
    """
    Extract selectable text. If low text, OCR rendered pages (scanned PDF fallback).
    """
    max_pages = int(settings.max_pdf_pages)
    doc = fitz.open(stream=data, filetype="pdf")

    n_pages = min(len(doc), max_pages)
    page_summaries: List[Dict[str, Any]] = []
    total_text_chars = 0

    # 1) try text extraction per page
    page_texts: List[str] = []
    for i in range(n_pages):
        page = doc.load_page(i)
        txt = page.get_text("text") or ""
        txt = _clean_text(txt)
        page_texts.append(txt)
        total_text_chars += len(txt)

    # Heuristic: if most pages have almost no text -> scanned
    scanned_like = total_text_chars < max(800, 80 * n_pages)

    ocr_texts: List[str] = []
    if scanned_like:
        # 2) render + OCR each page
        for i in range(n_pages):
            page = doc.load_page(i)
            pix = page.get_pixmap(dpi=200)  # decent OCR quality
            # pix to PIL
            from PIL import Image  # type: ignore

            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            ocr = _ocr_text_from_pil_image(img)
            ocr = _clean_text(ocr)
            ocr_texts.append(ocr)

    # Build a compact “finding summary”
    # Keep it short; the LLM prompt should see page highlights, not entire PDF dumps.
    if not scanned_like:
        key_excerpt = "\n".join([t[:600] for t in page_texts if t][:3]).strip()
        summary = (
            f"PDF analyzed ({n_pages} page(s)). Extracted selectable text.\n"
            f"Top excerpts:\n{key_excerpt if key_excerpt else '(no excerpt)'}"
        )
        data_out: Dict[str, Any] = {
            "pages": n_pages,
            "mode": "text",
            "page_text_samples": [
                {"page": idx + 1, "text": page_texts[idx][:1200]}
                for idx in range(min(n_pages, 5))
                if page_texts[idx]
            ],
        }
    else:
        key_excerpt = "\n".join([t[:600] for t in ocr_texts if t][:3]).strip()
        summary = (
            f"PDF analyzed ({n_pages} page(s)). Low selectable text; used OCR on rendered pages.\n"
            f"Top OCR excerpts:\n{key_excerpt if key_excerpt else '(no excerpt)'}"
        )
        data_out = {
            "pages": n_pages,
            "mode": "ocr",
            "page_ocr_samples": [
                {"page": idx + 1, "text": ocr_texts[idx][:1200]}
                for idx in range(min(n_pages, 5))
                if ocr_texts[idx]
            ],
        }

    doc.close()

    return AttachmentFinding(
        url=url,
        kind="pdf",
        summary=summary.strip(),
        data=data_out,
    )