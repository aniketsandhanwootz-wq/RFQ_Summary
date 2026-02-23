from __future__ import annotations

import base64
import re
from typing import Any, Dict, List

import fitz  # type: ignore
from PIL import Image  # type: ignore

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..config import Settings
from ..schema import AttachmentFinding
from .image import _ocr_text_from_pil_image


def _clean_text(s: str) -> str:
    s = (s or "").replace("\x00", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _claude_vision_text(settings: Settings, img_bytes: bytes, instruction: str) -> str:
    if not settings.enable_claude_vision_fallback:
        return ""
    if not (settings.anthropic_api_key or "").strip():
        return ""

    llm = ChatAnthropic(
        model=settings.anthropic_model,
        anthropic_api_key=settings.anthropic_api_key,
        temperature=0.2,
        max_tokens=1400,
    )

    b64 = base64.b64encode(img_bytes).decode("utf-8")
    msg = HumanMessage(
        content=[
            {"type": "text", "text": instruction},
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": b64},
            },
        ]
    )

    resp = llm.invoke([SystemMessage(content="You are a manufacturing RFQ analyst."), msg])
    return (resp.content or "").strip()


def analyze_pdf_bytes(settings: Settings, url: str, data: bytes) -> AttachmentFinding:
    max_pages = int(settings.max_pdf_pages)
    doc = fitz.open(stream=data, filetype="pdf")
    n_pages = min(len(doc), max_pages)

    page_text_samples: List[Dict[str, Any]] = []
    page_ocr_samples: List[Dict[str, Any]] = []
    page_vision_samples: List[Dict[str, Any]] = []

    total_text_chars = 0
    page_texts: List[str] = []

    # 1) selectable text
    for i in range(n_pages):
        page = doc.load_page(i)
        txt = _clean_text(page.get_text("text") or "")
        page_texts.append(txt)
        total_text_chars += len(txt)

    avg_text = total_text_chars / max(1, n_pages)
    scanned_like = avg_text < settings.min_pdf_text_chars_per_page

    for idx in range(min(n_pages, 5)):
        if page_texts[idx]:
            page_text_samples.append({"page": idx + 1, "text": page_texts[idx][:1400]})

    # 2) OCR + 3) Claude vision fallback
    if scanned_like:
        for i in range(n_pages):
            page = doc.load_page(i)
            pix = page.get_pixmap(dpi=220)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            ocr = _clean_text(_ocr_text_from_pil_image(img))
            if ocr:
                page_ocr_samples.append({"page": i + 1, "text": ocr[:1400]})

            if len(ocr) < settings.min_ocr_chars_to_accept:
                try:
                    png_bytes = pix.tobytes("png")
                    vision = _claude_vision_text(
                        settings,
                        png_bytes,
                        instruction=(
                            "This is a PDF page from an RFQ drawing/spec. Extract any specs, dimensions, tolerances, "
                            "materials, part numbers, and notes. Return concise bullets only."
                        ),
                    )
                    vision = (vision or "").strip()
                    if vision:
                        page_vision_samples.append({"page": i + 1, "text": vision[:1800]})
                except Exception:
                    pass

    doc.close()

    if not scanned_like:
        excerpt = "\n".join([t[:700] for t in page_texts if t][:3]).strip()
        summary = (
            f"PDF analyzed ({n_pages} page(s)). Selectable text extracted.\n"
            f"Top excerpts:\n{excerpt if excerpt else '(no excerpt)'}"
        )
        data_out = {
            "pages": n_pages,
            "mode": "text",
            "page_text_samples": page_text_samples,
        }
    else:
        excerpt_ocr = "\n".join([d["text"][:700] for d in page_ocr_samples][:2]).strip()
        excerpt_vis = "\n".join([d["text"][:700] for d in page_vision_samples][:2]).strip()
        summary = (
            f"PDF analyzed ({n_pages} page(s)). Low selectable text; OCR + Claude vision fallback applied.\n"
            f"OCR excerpt:\n{excerpt_ocr if excerpt_ocr else '(none)'}\n\n"
            f"Vision excerpt:\n{excerpt_vis if excerpt_vis else '(none)'}"
        )
        data_out = {
            "pages": n_pages,
            "mode": "ocr+vision",
            "page_ocr_samples": page_ocr_samples[:8],
            "page_vision_samples": page_vision_samples[:8],
        }

    return AttachmentFinding(
        url=url,
        kind="pdf",
        summary=summary.strip(),
        data=data_out,
    )