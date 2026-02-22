from __future__ import annotations

from pathlib import Path
from typing import List

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from .config import Settings


def load_prompt_file(path: str) -> str:
    p = Path(path).expanduser().resolve()
    return p.read_text(encoding="utf-8")


def generate_text(settings: Settings, system_prompt: str, user_prompt: str) -> str:
    if not settings.gemini_api_key.strip():
        raise RuntimeError("Missing GEMINI_API_KEY")

    models = [settings.gemini_model] + [
        m.strip() for m in (settings.gemini_model_fallbacks or "").split(",") if m.strip()
    ]

    last_err: Exception | None = None
    for model in models:
        try:
            llm = ChatGoogleGenerativeAI(
                model=model,
                google_api_key=settings.gemini_api_key,
                temperature=0.2,
            )
            resp = llm.invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]
            )
            return (resp.content or "").strip()
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"All GEMINI models failed. Last error: {last_err}")