from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from .config import Settings
from .schema import OutputPayload


def write_output(settings: Settings, out: OutputPayload) -> str:
    """
    Returns the base path (without extension) for convenience.
    """
    mode = (settings.output_mode or "local").strip().lower()
    if mode != "local":
        raise NotImplementedError("Only OUTPUT_MODE=local is implemented in Part 1")

    out_dir = Path(settings.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    safe_title = "".join([c if c.isalnum() or c in ("-", "_") else "_" for c in out.rfq_title])[:60]
    base = out_dir / f"{safe_title}_{out.run_id}_{ts}"

    # JSON
    with open(str(base) + ".json", "w", encoding="utf-8") as f:
        f.write(out.model_dump_json(indent=2))

    # Markdown
    md = out.summary_md.strip() + "\n"
    with open(str(base) + ".md", "w", encoding="utf-8") as f:
        f.write(md)

    return str(base)