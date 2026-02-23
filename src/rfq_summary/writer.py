from __future__ import annotations

import json
from typing import Dict

from .config import Settings
from .schema import InputPayload, OutputPayload
from .glide_client import glide_set_columns
from .gsheet_logger import append_rows, build_chunked_log_rows


def _print_terminal(out: OutputPayload) -> None:
    print("\n==============================")
    print(f"MODE: {out.mode}  RUN_ID: {out.run_id}  ROW_ID: {out.row_id}")
    print("==============================\n")

    if out.mode == "pricing":
        print("=== OUTPUT 1 (Pricing Estimate) ===\n")
        print(out.pricing_estimate_text or "")
        print("\n=== OUTPUT 2 (Reasoning) ===\n")
        print(out.pricing_reasoning_text or "")
    else:
        # Updated summary prompt: single output only
        print("=== OUTPUT (Strategic Briefing & Nudges) ===\n")
        print(out.rfq_summary_text or "")

    print("\n==============================\n")


def write_all(settings: Settings, inp: InputPayload, out: OutputPayload) -> None:
    """
    - If ENABLE_GLIDE_WRITEBACK=true: write to Glide first, then log to Sheets.
    - If ENABLE_GLIDE_WRITEBACK=false: print to terminal (safe), then log to Sheets.
    - Logging is chunked so we don't lose any data.
    """

    colvals: Dict[str, str] = {}

    if out.mode == "pricing":
        # Prompt 1: OUTPUT 1 -> Pricing estimate, OUTPUT 2 -> Pricing reasoning
        colvals[settings.glide_col_price_estimate] = out.pricing_estimate_text or ""
        colvals[settings.glide_col_price_reasoning] = out.pricing_reasoning_text or ""

    elif out.mode == "summary":
        # Updated Prompt 2: single output -> RFQ Summary ONLY
        colvals[settings.glide_col_rfq_summary] = out.rfq_summary_text or ""

        # IMPORTANT: do NOT touch pricing columns in summary mode
        # (prevents overwriting PRfRY/jblXm)

    else:
        raise RuntimeError(f"Unknown mode: {out.mode}")

    # 1) Writeback OR terminal print
    if settings.enable_glide_writeback:
        if not out.row_id.strip():
            raise RuntimeError("row_id missing but ENABLE_GLIDE_WRITEBACK=true")
        glide_set_columns(settings, out.row_id, colvals)
    else:
        _print_terminal(out)

    # 2) Build log fields (store everything; chunked rows preserve all)
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

    web_text = ""
    if out.web_findings:
        web_text = "\n\n".join([f"{w.title} {w.url}\n{w.snippet}".strip() for w in out.web_findings])

    fields = {
        "input_json": input_json,
        "extracted_attachment_text": extracted_text,
        "pricing_estimate_text": out.pricing_estimate_text or "",
        "pricing_reasoning_text": out.pricing_reasoning_text or "",
        "rfq_summary_text": out.rfq_summary_text or "",
        "raw_model_output": out.raw_model_output or "",
        "web_findings": web_text,
        "glide_column_values": json.dumps(colvals, ensure_ascii=False),
        "writeback_enabled": str(bool(settings.enable_glide_writeback)),
    }

    rows = build_chunked_log_rows(
        settings=settings,
        run_id=out.run_id,
        mode=out.mode,
        row_id=out.row_id,
        fields=fields,
    )
    append_rows(settings, rows)