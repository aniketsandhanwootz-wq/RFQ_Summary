from __future__ import annotations

import os
import uvicorn


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))

    # PROD-SAFE: never enable reload on Render (prevents restart loops + 502s)
    uvicorn.run(
        "rfq_summary.api:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level=(os.getenv("LOG_LEVEL", "info") or "info").lower(),
        # small hardening defaults
        access_log=True,
    )