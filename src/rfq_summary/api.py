from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from .config import load_settings
from .schema import InputPayload
from .task import run_pricing, run_summary
from .writer import write_all

app = FastAPI(title="RFQ Summary Service", version="0.1.0")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/")
def root():
    return {"ok": True, "service": "rfq-summary", "endpoints": ["/rfq/pricing", "/rfq/summary", "/health"]}


def _require_row_id_if_writeback(settings, obj: InputPayload):
    if settings.enable_glide_writeback and not (obj.row_id or "").strip():
        raise HTTPException(status_code=400, detail="Missing rowID/row_id in payload (required when writeback enabled).")


def _unwrap_payload(payload: dict) -> dict:
    """
    Glide can send nested bodies like:
      { "RFQ Final json": { ... } }
    This unwraps common wrappers.
    """
    if not isinstance(payload, dict):
        return payload

    for k in ("RFQ Final json", "rfq_final_json", "rfq_json", "data", "payload"):
        inner = payload.get(k)
        if isinstance(inner, dict) and ("Title" in inner or "Product_json" in inner):
            return inner

    if len(payload) == 1:
        only_val = next(iter(payload.values()))
        if isinstance(only_val, dict):
            return only_val

    return payload


def _validate(payload: dict) -> InputPayload:
    try:
        return InputPayload.model_validate(payload)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()) from e


@app.post("/rfq/pricing")
def rfq_pricing(payload: dict):
    settings = load_settings()
    data = _unwrap_payload(payload)
    obj = _validate(data)
    _require_row_id_if_writeback(settings, obj)

    out = run_pricing(settings, obj)
    write_all(settings, obj, out)
    return {"ok": True, "run_id": out.run_id, "mode": out.mode}


@app.post("/rfq/summary")
def rfq_summary(payload: dict):
    settings = load_settings()
    data = _unwrap_payload(payload)
    obj = _validate(data)
    _require_row_id_if_writeback(settings, obj)

    out = run_summary(settings, obj)
    write_all(settings, obj, out)
    return {"ok": True, "run_id": out.run_id, "mode": out.mode}