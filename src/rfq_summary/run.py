from __future__ import annotations

import os
import uvicorn


def _truthy(v: str) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "y", "on")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    # NEVER reload in production (Render). Turn on only locally when you want.
    reload = _truthy(os.getenv("DEV_RELOAD", "false"))

    uvicorn.run(
        "rfq_summary.api:app",
        host="0.0.0.0",
        port=port,
        reload=reload,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )