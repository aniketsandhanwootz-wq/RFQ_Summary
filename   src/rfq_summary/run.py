from __future__ import annotations

import json
import sys
from pathlib import Path
from rich import print

from .config import load_settings
from .schema import InputPayload
from .task import run_task


def main() -> int:
    if len(sys.argv) < 2:
        print("[red]Usage:[/red] python -m rfq_summary.run <input.json>")
        return 2

    p = Path(sys.argv[1]).expanduser().resolve()
    if not p.exists():
        print(f"[red]Input file not found:[/red] {p}")
        return 2

    raw = json.loads(p.read_text(encoding="utf-8"))
    payload = InputPayload.model_validate(raw)

    settings = load_settings()
    out = run_task(settings, payload)

    print("[green]DONE[/green]")
    print(f"run_id: {out.run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())