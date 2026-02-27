from __future__ import annotations

import base64

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..config import Settings
from ..schema import AttachmentFinding


def _guess_image_mime(data: bytes) -> str:
    """
    Minimal MIME sniffing without imghdr (removed in Py3.13).
    """
    b = data[:16] if data else b""

    # PNG
    if b.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    # JPEG
    if b.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    # WEBP (RIFF....WEBP)
    if len(b) >= 12 and b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    # GIF
    if b.startswith(b"GIF87a") or b.startswith(b"GIF89a"):
        return "image/gif"

    # Safe default
    return "image/png"

def _claude_vision_text(settings: Settings, img_bytes: bytes, instruction: str) -> str:
    if not getattr(settings, "enable_claude_vision_fallback", False):
        return ""
    if not (getattr(settings, "anthropic_api_key", "") or "").strip():
        return ""
    if not (getattr(settings, "anthropic_model", "") or "").strip():
        return ""

    llm = ChatAnthropic(
        model=settings.anthropic_model,
        anthropic_api_key=settings.anthropic_api_key,
        temperature=0.2,
        max_tokens=1200,
    )


    b64 = base64.b64encode(img_bytes).decode("utf-8")
    mime = _guess_image_mime(img_bytes)
    msg = HumanMessage(
        content=[
            {"type": "text", "text": instruction},
            {
                "type": "image",
                "source": {"type": "base64", "media_type": mime, "data": b64},
            },
        ]
    )

    resp = llm.invoke([SystemMessage(content="You are a manufacturing RFQ analyst."), msg])
    return (resp.content or "").strip()

def analyze_image_bytes(settings: Settings, url: str, data: bytes) -> AttachmentFinding:
    vision = ""
    if getattr(settings, "enable_claude_vision_fallback", False):
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

    # Build extracted_text (bounded) for task.py consumption
    MAX_IMAGE_TEXT_CHARS = 25_000
    blocks = [f"## IMAGE: {url}"]
    if vision.strip():
        blocks.append("VISION:\n" + vision.strip())
    else:
        blocks.append("VISION:\n(no vision output)")

    extracted_text = "\n\n".join(blocks).strip()
    if len(extracted_text) > MAX_IMAGE_TEXT_CHARS:
        extracted_text = extracted_text[: MAX_IMAGE_TEXT_CHARS - 80] + "\n\n...[TRUNCATED]..."

    summary = vision.strip() if vision.strip() else "Image analyzed. No vision output available."

    return AttachmentFinding(
        url=url,
        kind="image",
        summary=summary,
        data={
            "has_vision": bool(vision.strip()),
            "extracted_text": extracted_text,
        },
    )