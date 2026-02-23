from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Literal

from fastapi import FastAPI, HTTPException, Response
from pydantic import ValidationError

from .config import load_settings, Settings
from .schema import InputPayload
from .task import run_pricing, run_summary
from .writer import write_all
from .gsheet_logger import log_job_event

Mode = Literal["pricing", "summary"]


@dataclass(frozen=True)
class Job:
    run_id: str
    mode: Mode
    payload: Dict[str, Any]  # already unwrapped
    row_id: str


app = FastAPI(title="RFQ Summary Service", version="0.1.0")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/")
def root():
    return {"ok": True, "service": "rfq-summary", "endpoints": ["/rfq/pricing", "/rfq/summary", "/health"]}


@app.head("/")
def root_head():
    # Render health checks often hit HEAD /
    return Response(status_code=200)


# -----------------------
# Payload helpers
# -----------------------
def _require_row_id_if_writeback(settings: Settings, obj: InputPayload):
    if settings.enable_glide_writeback and not (obj.row_id or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Missing rowID/row_id in payload (required when writeback enabled).",
        )


def _unwrap_payload(payload: dict) -> dict:
    """
    Glide can send nested bodies like:
      { "RFQ Final json": { ... } }
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


# -----------------------
# In-memory queue + dispatcher
# -----------------------
def _get_queue() -> asyncio.Queue[Job]:
    q = getattr(app.state, "job_queue", None)
    if q is None:
        q = asyncio.Queue()
        app.state.job_queue = q
    return q


def _get_semaphore(settings: Settings) -> asyncio.Semaphore:
    sem = getattr(app.state, "job_semaphore", None)
    if sem is None:
        sem = asyncio.Semaphore(max(1, int(settings.max_concurrent_jobs)))
        app.state.job_semaphore = sem
    return sem


def _queue_size() -> int:
    return _get_queue().qsize()


async def _run_job(job: Job) -> None:
    settings = load_settings()

    # RUNNING (best-effort)
    try:
        log_job_event(settings, job.run_id, job.mode, job.row_id, status="RUNNING", message="Job started")
    except Exception:
        pass

    try:
        obj = _validate(job.payload)
        _require_row_id_if_writeback(settings, obj)

        async def _do_work():
            if job.mode == "pricing":
                out = await asyncio.to_thread(run_pricing, settings, obj, job.run_id)
            else:
                out = await asyncio.to_thread(run_summary, settings, obj, job.run_id)

            await asyncio.to_thread(write_all, settings, obj, out)

        await asyncio.wait_for(_do_work(), timeout=max(30, int(settings.job_timeout_sec)))

        # DONE (best-effort)
        try:
            log_job_event(settings, job.run_id, job.mode, job.row_id, status="DONE", message="Job completed")
        except Exception:
            pass

    except asyncio.TimeoutError:
        try:
            log_job_event(
                settings,
                job.run_id,
                job.mode,
                job.row_id,
                status="FAILED",
                message=f"Job timeout after {settings.job_timeout_sec}s",
            )
        except Exception:
            pass

    except Exception as e:
        try:
            log_job_event(
                settings,
                job.run_id,
                job.mode,
                job.row_id,
                status="FAILED",
                message=f"{type(e).__name__}: {e}",
            )
        except Exception:
            pass


async def _dispatcher_loop() -> None:
    while True:
        job = await _get_queue().get()
        settings = load_settings()
        sem = _get_semaphore(settings)

        await sem.acquire()

        async def _wrapped():
            try:
                await _run_job(job)
            finally:
                sem.release()

        # fire-and-forget, but safe
        asyncio.create_task(_wrapped())


@app.on_event("startup")
async def _startup():
    # start dispatcher exactly once
    if getattr(app.state, "dispatcher_started", False):
        return
    app.state.dispatcher_started = True
    asyncio.create_task(_dispatcher_loop())


async def _enqueue_or_reject(mode: Mode, data: dict, obj: InputPayload) -> Dict[str, Any]:
    settings = load_settings()
    max_q = max(1, int(settings.max_queue_size))

    run_id = uuid.uuid4().hex[:10]
    row_id = (obj.row_id or "").strip()

    if _queue_size() >= max_q:
        # Log reject WITHOUT huge payload
        try:
            log_job_event(
                settings,
                run_id=run_id,
                mode=mode,
                row_id=row_id,
                status="REJECTED_QUEUE_FULL",
                message=f"Queue full: qsize={_queue_size()} max={max_q}",
            )
        except Exception:
            pass

        raise HTTPException(
            status_code=429,
            detail={
                "ok": False,
                "run_id": run_id,
                "status": "rejected",
                "reason": "QUEUE_FULL",
                "retry_hint": "Try again in 2-3 minutes.",
            },
        )

    job = Job(run_id=run_id, mode=mode, payload=data, row_id=row_id)
    await _get_queue().put(job)

    try:
        log_job_event(
            settings,
            run_id,
            mode,
            row_id,
            status="QUEUED",
            message=f"Queued (qsize={_queue_size()}/{max_q})",
        )
    except Exception:
        pass

    return {
        "ok": True,
        "run_id": run_id,
        "status": "queued",
        "mode": mode,
        "queue": {"qsize": _queue_size(), "max": max_q},
    }


# -----------------------
# Endpoints
# -----------------------
@app.post("/rfq/pricing")
async def rfq_pricing(payload: dict, response: Response):
    settings = load_settings()
    data = _unwrap_payload(payload)
    obj = _validate(data)
    _require_row_id_if_writeback(settings, obj)

    ack = await _enqueue_or_reject("pricing", data, obj)
    response.status_code = 202
    return ack


@app.post("/rfq/summary")
async def rfq_summary(payload: dict, response: Response):
    settings = load_settings()
    data = _unwrap_payload(payload)
    obj = _validate(data)
    _require_row_id_if_writeback(settings, obj)

    ack = await _enqueue_or_reject("summary", data, obj)
    response.status_code = 202
    return ack