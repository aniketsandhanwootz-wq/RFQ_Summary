from __future__ import annotations

import base64
from io import BytesIO

from PIL import Image  # type: ignore

from langchain_anthropic import ChatAnthropic
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


def _claude_vision_text(settings: Settings, img_bytes: bytes, instruction: str) -> str:
    if not settings.enable_claude_vision_fallback:
        return ""
    if not (settings.anthropic_api_key or "").strip():
        return ""

    llm = ChatAnthropic(
        model=settings.anthropic_model,
        anthropic_api_key=settings.anthropic_api_key,
        temperature=0.2,
        max_tokens=1200,
    )

    b64 = base64.b64encode(img_bytes).decode("utf-8")

    # Anthropic multimodal message format (supported by langchain-anthropic)
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


def analyze_image_bytes(settings: Settings, url: str, data: bytes) -> AttachmentFinding:
    img = Image.open(BytesIO(data)).convert("RGB")
    ocr_text = _ocr_text_from_pil_image(img).strip()

    vision = ""
    if len(ocr_text) < settings.min_ocr_chars_to_accept:
        try:
            vision = _claude_vision_text(
                settings,
                data,
                instruction=(
                    "Extract any specs/dimensions/material/part numbers/notes visible in the image. "
                    "Return concise bullet points only."
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