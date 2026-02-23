from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import List, Dict

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from .config import Settings

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _chunks(s: str, size: int) -> List[str]:
    s = s or ""
    if size <= 0:
        return [s]
    return [s[i : i + size] for i in range(0, len(s), size)] or [""]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sheet_service(settings: Settings):
    sa_json = base64.b64decode(settings.google_sa_json_b64).decode("utf-8")
    info = json.loads(sa_json)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def append_rows(settings: Settings, rows: List[List[str]]) -> None:
    if not settings.enable_sheets_logging:
        return
    if not settings.log_sheet_id or not settings.google_sa_json_b64:
        return
    if not rows:
        return

    try:
        service = _sheet_service(settings)
        rng = f"{settings.log_sheet_tab}!A:H"
        body = {"values": rows}
        service.spreadsheets().values().append(
            spreadsheetId=settings.log_sheet_id,
            range=rng,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body=body,
        ).execute()
    except Exception:
        # Never crash the worker due to logging.
        return


def build_chunked_log_rows(
    settings: Settings,
    run_id: str,
    mode: str,
    row_id: str,
    fields: Dict[str, str],
) -> List[List[str]]:
    """
    Row schema (8 cols):
      ts, run_id, mode, row_id, chunk_index, chunk_total, field_name, chunk_text
    """
    ts = _now_iso()
    max_chars = int(settings.max_cell_chars)

    out_rows: List[List[str]] = []
    for field_name, text in fields.items():
        parts = _chunks(text or "", max_chars)
        total = len(parts)
        for i, part in enumerate(parts, start=1):
            out_rows.append([ts, run_id, mode, row_id or "", str(i), str(total), field_name, part])
    return out_rows


def log_job_event(
    settings: Settings,
    run_id: str,
    mode: str,
    row_id: str,
    status: str,
    message: str = "",
) -> None:
    """
    Minimal status transitions only.
    No payload logging here (avoid huge sheet writes).
    """
    if not settings.enable_sheets_logging:
        return

    event_text = f"STATUS={status}\n{message or ''}".strip()

    rows = build_chunked_log_rows(
        settings=settings,
        run_id=run_id,
        mode=mode,
        row_id=row_id or "",
        fields={"job_event": event_text},
    )
    append_rows(settings, rows)