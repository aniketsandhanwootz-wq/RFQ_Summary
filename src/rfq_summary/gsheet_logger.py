from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import List

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from .config import Settings


SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _clip(s: str, max_chars: int) -> str:
    s = s or ""
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 60] + "\n\n...[TRUNCATED]..."


def append_log_row(settings: Settings, values: List[str]) -> None:
    if not settings.log_sheet_id or not settings.google_sa_json_b64:
        return  # logging optional

    sa_json = base64.b64decode(settings.google_sa_json_b64).decode("utf-8")
    info = json.loads(sa_json)

    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    service = build("sheets", "v4", credentials=creds, cache_discovery=False)

    rng = f"{settings.log_sheet_tab}!A:Z"
    body = {"values": [values]}
    service.spreadsheets().values().append(
        spreadsheetId=settings.log_sheet_id,
        range=rng,
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body=body,
    ).execute()


def build_log_row(settings: Settings, mode: str, row_id: str, input_json: str, extracted_text: str, output_text: str, raw_model: str) -> List[str]:
    ts = datetime.now(timezone.utc).isoformat()
    m = settings.max_cell_chars

    return [
        ts,
        mode,
        row_id,
        _clip(input_json, m),
        _clip(extracted_text, m),
        _clip(output_text, m),
        _clip(raw_model, m),
    ]