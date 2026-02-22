from __future__ import annotations

import httpx
from .config import Settings


def glide_set_columns(settings: Settings, row_id: str, column_values: dict) -> None:
    if not settings.glide_api_key or not settings.glide_app_id or not settings.glide_rfq_table:
        raise RuntimeError("Missing GLIDE_* env vars (api_key/app_id/table).")

    url = "https://api.glideapp.io/api/function/mutateTables"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.glide_api_key}",
    }

    payload = {
        "appID": settings.glide_app_id,
        "mutations": [
            {
                "kind": "set-columns-in-row",
                "tableName": settings.glide_rfq_table,
                "rowID": row_id,
                "columnValues": column_values,
            }
        ],
    }

    with httpx.Client(timeout=60) as client:
        r = client.post(url, headers=headers, json=payload)
        r.raise_for_status()