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


@app.post("/rfq/pricing")
def rfq_pricing(payload: dict):
    settings = load_settings()
    obj = InputPayload.model_validate(payload)
    if not obj.row_id.strip():
        raise HTTPException(status_code=400, detail="Missing rowID in payload (required for Glide writeback).")

    out = run_pricing(settings, obj)
    write_all(settings, obj, out)
    return {"ok": True, "run_id": out.run_id, "mode": out.mode}


@app.post("/rfq/summary")
def rfq_summary(payload: dict):
    settings = load_settings()
    obj = InputPayload.model_validate(payload)
    if not obj.row_id.strip():
        raise HTTPException(status_code=400, detail="Missing rowID in payload (required for Glide writeback).")

    out = run_summary(settings, obj)
    write_all(settings, obj, out)
    return {"ok": True, "run_id": out.run_id, "mode": out.mode}