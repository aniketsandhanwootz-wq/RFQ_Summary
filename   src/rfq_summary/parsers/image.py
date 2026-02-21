from __future__ import annotations

from typing import Dict, Any, Optional
import base64

from PIL import Image  # type: ignore
from io import BytesIO

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from ..config import Settings
from ..schema import AttachmentFinding


def _try_import_tesseract():
    try:
        import pytesseract  # type: ignore
        return pytesseract
    except Exception:
        return None


def _ocr_text_from_pil_image(img: Image.Image) -> str:
    pytesseract = _try_import_tesseract()
    if not pytesseract:
        return ""
    try:
        return pytesseract.image_to_string(img)
    except Exception:
        return ""


def _gemini_caption(settings: Settings, img_bytes: bytes) -> str:
    """
    Optional vision caption using Gemini multimodal.
    If your model/key doesn’t support vision, it will fail gracefully (caller handles).
    """
    if not settings.gemini_api_key.strip():
        return ""

    llm = ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.gemini_api_key,
        temperature=0.2,
    )

    b64 = base64.b64encode(img_bytes).decode("utf-8")
    # LangChain Google GenAI supports "image_url" parts in HumanMessage content.
    msg = HumanMessage(
        content=[
            {"type": "text", "text": "Describe this image for an RFQ. Extract any visible specs/dimensions/labels."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]
    )
    resp = llm.invoke([SystemMessage(content="You are a manufacturing RFQ analyst."), msg])
    return (resp.content or "").strip()


def analyze_image_bytes(settings: Settings, url: str, data: bytes) -> AttachmentFinding:
    """
    OCR + optional vision caption (Gemini).
    """
    img = Image.open(BytesIO(data)).convert("RGB")

    ocr_text = _ocr_text_from_pil_image(img).strip()

    caption = ""
    try:
        caption = _gemini_caption(settings, data)
    except Exception:
        caption = ""

    summary_parts = []
    if caption:
        summary_parts.append(f"Vision caption: {caption}")
    if ocr_text:
        summary_parts.append(f"OCR text (partial): {ocr_text[:1200]}")
    if not summary_parts:
        summary_parts.append("Image analyzed. No OCR/vision output available (OCR not installed or vision not enabled).")

    return AttachmentFinding(
        url=url,
        kind="image",
        summary="\n".join(summary_parts).strip(),
        data={"has_ocr": bool(ocr_text), "has_caption": bool(caption)},
    )