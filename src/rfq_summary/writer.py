from __future__ import annotations

import json

from .config import Settings
from .schema import InputPayload, OutputPayload
from .glide_client import glide_set_columns
from .gsheet_logger import append_log_row, build_log_row


def write_all(settings: Settings, inp: InputPayload, out: OutputPayload) -> None:
    """
    Writes results to Glide columns and appends a log row in Google Sheets.
    """

    # 1) Glide writeback mapping
    colvals = {}
    if out.mode == "pricing":
        # write estimate + reasoning
        colvals[settings.glide_col_price_estimate] = out.pricing_estimate_text or ""
        colvals[settings.glide_col_price_reasoning] = out.pricing_reasoning_text or ""
    elif out.mode == "summary":
        # write RFQ summary + also write pricing estimate (if present)
        colvals[settings.glide_col_rfq_summary] = out.rfq_summary_text or ""
        if out.pricing_estimate_text:
            colvals[settings.glide_col_price_estimate] = out.pricing_estimate_text
        # if you want OUTPUT2 to also go in reasoning column, uncomment:
        # colvals[settings.glide_col_price_reasoning] = out.rfq_summary_text or ""
    else:
        raise RuntimeError(f"Unknown mode: {out.mode}")

    glide_set_columns(settings, out.row_id, colvals)

    # 2) Google Sheet logging (single row)
    input_json = json.dumps(
        {
            "rowID": inp.row_id,
            "Title": inp.title,
            "Industry": inp.industry,
            "Geography": inp.geography,
            "Standard": inp.standard,
            "Customer name": inp.customer_name,
            "Product_json": inp.product_json,
        },
        ensure_ascii=False,
    )

    extracted_text = inp.extracted_attachment_text or ""
    output_text = out.raw_model_output or ""

    row = build_log_row(
        settings=settings,
        mode=out.mode,
        row_id=out.row_id,
        input_json=input_json,
        extracted_text=extracted_text,
        output_text=output_text,
        raw_model=out.raw_model_output or "",
    )
    append_log_row(settings, row)