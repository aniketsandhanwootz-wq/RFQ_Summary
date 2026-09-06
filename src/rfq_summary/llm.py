from __future__ import annotations

import re
from pathlib import Path
from typing import List

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage

from .config import Settings


def load_prompt_file(path: str) -> str:
    p = Path(path).expanduser().resolve()
    return p.read_text(encoding="utf-8")


# Adaptive thinking is accepted by Opus 4.6+ / Sonnet 4.6+ / Opus 5 / Sonnet 5 and
# rejected with a 400 by everything older, Haiku 4.5 included — it still takes the
# older budget_tokens form. Sending it to a model that cannot take it turns that
# fallback into a guaranteed failure, which is the opposite of what a fallback is for.
_ADAPTIVE_THINKING_MODELS = re.compile(
    r"^claude-(?:fable|mythos)-\d|^claude-opus-(?:5|4-(?:6|7|8))|^claude-sonnet-(?:5|4-6)"
)


def _supports_adaptive_thinking(model: str) -> bool:
    return bool(_ADAPTIVE_THINKING_MODELS.match((model or "").strip()))


def _models(settings: Settings) -> List[str]:
    primary = (settings.anthropic_model or "").strip()
    fallbacks = [m.strip() for m in (settings.anthropic_model_fallbacks or "").split(",") if m.strip()]
    out = []
    if primary:
        out.append(primary)
    out.extend([m for m in fallbacks if m and m not in out])
    return out


def generate_text(
    settings: Settings,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int | None = None,
) -> str:
    if not (settings.anthropic_api_key or "").strip():
        raise RuntimeError("Missing ANTHROPIC_API_KEY")

    models = _models(settings)
    primary = models[0] if models else ""

    # Opus 5, Opus 4.8/4.7 and Sonnet 5 reject `temperature` with a 400, so it is
    # not sent at all. Adaptive thinking is the replacement lever, but only on the
    # models that accept it — see _supports_adaptive_thinking.
    failures: List[str] = []
    last_err: Exception | None = None

    for model in models:
        kwargs: dict = {}
        if settings.anthropic_adaptive_thinking and _supports_adaptive_thinking(model):
            kwargs["thinking"] = {"type": "adaptive"}

        try:
            llm = ChatAnthropic(
                model=model,
                anthropic_api_key=settings.anthropic_api_key,
                max_tokens=8000 if max_tokens is None else max(1000, int(max_tokens)),
                **kwargs,
            )
            resp = llm.invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]
            )
            # A silent fallback is a quietly worse answer. Say which model replied.
            if model != primary:
                print(f"[WARN] llm | {primary} failed, answered by fallback {model}. Earlier: {'; '.join(failures)}")
            return (resp.content or "").strip()
        except Exception as e:
            last_err = e
            detail = f"{model}: {type(e).__name__}: {e}"
            failures.append(detail)
            print(f"[WARN] llm | model {detail}")

    # Every model's error, not just the last. A retired model at the end of the
    # chain always 404s, and reporting only that hides why the primary failed.
    missing = [f for f in failures if "not_found_error" in f or "404" in f]
    hint = ""
    if missing:
        names = ", ".join(f.split(":", 1)[0] for f in missing)
        hint = (
            f" NOTE: {names} returned not_found — the model id does not exist or is retired. "
            f"Fix ANTHROPIC_MODEL / ANTHROPIC_MODEL_FALLBACKS rather than reading this as an outage."
        )
    raise RuntimeError(
        f"All {len(models)} Claude models failed. Each failure: {' | '.join(failures)}.{hint}"
    ) from last_err
