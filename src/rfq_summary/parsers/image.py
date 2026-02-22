from __future__ import annotations

import base64
from io import BytesIO
from typing import Optional

from PIL import Image  # type: ignore

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


def _gemini_vision_text(settings: Settings, img_bytes: bytes, instruction: str) -> str:
    if not settings.enable_gemini_vision_fallback:
        return ""
    if not settings.gemini_api_key.strip():
        return ""

    llm = ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.gemini_api_key,
        temperature=0.2,
    )

    b64 = base64.b64encode(img_bytes).decode("utf-8")
    msg = HumanMessage(
        content=[
            {"type": "text", "text": instruction},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]
    )
    resp = llm.invoke([SystemMessage(content="You are a manufacturing RFQ analyst."), msg])
    return (resp.content or "").strip()


def analyze_image_bytes(settings: Settings, url: str, data: bytes) -> AttachmentFinding:
    img = Image.open(BytesIO(data)).convert("RGB")
    ocr_text = _ocr_text_from_pil_image(img).strip()

    vision = ""
    # run vision if OCR is missing/too short
    if len(ocr_text) < settings.min_ocr_chars_to_accept:
        try:
            vision = _gemini_vision_text(
                settings,
                data,
                instruction=(
                    "Extract any specs/dimensions/material/part numbers/notes visible in the image. "
                    "Return concise bullet points."
                ),
            )
        except Exception:
            vision = ""

    summary_parts = []
    if vision:
        summary_parts.append(f"Vision extraction:\n{vision}")
    if ocr_text:
        summary_parts.append(f"OCR text (partial): {ocr_text[:1200]}")
    if not summary_parts:
        summary_parts.append("Image analyzed. No OCR/vision output available.")

    return AttachmentFinding(
        url=url,
        kind="image",
        summary="\n\n".join(summary_parts).strip(),
        data={
            "has_ocr": bool(ocr_text),
            "has_vision": bool(vision),
            "ocr_chars": len(ocr_text),
        },
    )