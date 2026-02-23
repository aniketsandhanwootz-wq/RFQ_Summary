from __future__ import annotations

from fastapi import FastAPI, HTTPException
from .config import load_settings
from .schema import InputPayload
from .task import run_pricing, run_summary
from .writer import write_all

app = FastAPI(title="RFQ Summary Service", version="0.1.0")


@app.get("/health")
def health():
    return {"ok": True}


def _require_row_id_if_writeback(settings, obj: InputPayload):
    if settings.enable_glide_writeback and not obj.row_id.strip():
        raise HTTPException(status_code=400, detail="Missing rowID in payload (required when writeback enabled).")


@app.post("/rfq/pricing")
def rfq_pricing(payload: dict):
    settings = load_settings()
    obj = InputPayload.model_validate(payload)
    _require_row_id_if_writeback(settings, obj)

    out = run_pricing(settings, obj)
    write_all(settings, obj, out)
    return {"ok": True, "run_id": out.run_id, "mode": out.mode}


@app.post("/rfq/summary")
def rfq_summary(payload: dict):
    settings = load_settings()
    obj = InputPayload.model_validate(payload)
    _require_row_id_if_writeback(settings, obj)

    out = run_summary(settings, obj)
    write_all(settings, obj, out)
    return {"ok": True, "run_id": out.run_id, "mode": out.mode}