from __future__ import annotations

import json
import uuid
from typing import Tuple, List

from .config import Settings
from .schema import InputPayload, OutputPayload, WebFinding
from .attachments import analyze_attachments
from .search import PerplexitySearchClient
from .llm import load_prompt_file, generate_text


def _join_attachment_text(payload: InputPayload, attachment_findings) -> str:
    # prefer externally provided extracted text if present
    if (payload.extracted_attachment_text or "").strip():
        return payload.extracted_attachment_text.strip()

    # else build compact text from findings
    blocks = []
    for a in attachment_findings:
        blocks.append(f"[{a.kind}] {a.url}\n{a.summary}\n")
    return "\n".join(blocks).strip()


def _parse_two_outputs(model_text: str) -> Tuple[str, str]:
    """
    Parse sections:
      === OUTPUT 1: ... ===
      === OUTPUT 2: ... ===
    Fallback: return entire text as output2.
    """
    t = model_text or ""
    i1 = t.find("=== OUTPUT 1")
    i2 = t.find("=== OUTPUT 2")
    if i1 >= 0 and i2 > i1:
        out1 = t[i1:i2].strip()
        out2 = t[i2:].strip()
        return out1, out2
    return "", t.strip()


def _build_user_prompt(prompt_template: str, payload: InputPayload, extracted_text: str) -> str:
    rfq_json = {
        "Title": payload.title,
        "Industry": payload.industry,
        "Geography": payload.geography,
        "Standard": payload.standard,
        "Customer name": payload.customer_name,
        "Product_json": payload.product_json,
        "rowID": payload.row_id,
    }
    return (
        prompt_template
        .replace("{{insert_main_rfq_json_here}}", json.dumps(rfq_json, ensure_ascii=False))
        .replace("{{insert_extracted_text_from_power_automate_here}}", extracted_text or "")
    )


def run_pricing(settings: Settings, payload: InputPayload) -> OutputPayload:
    run_id = uuid.uuid4().hex[:10]

    attachment_findings = analyze_attachments(settings, payload.all_attachment_urls())
    extracted_text = _join_attachment_text(payload, attachment_findings)

    prompt_template = load_prompt_file(settings.prompt_pricing_file)

    # Web search is required for pricing prompt (live market)
    # Use a single initial web query to prime context; prompt itself also says "use web".
    web_findings: List[WebFinding] = []
    q = f"Wholesale unit pricing India for: {payload.title} | {payload.standard} | {payload.product.details if payload.product else ''}"
    web_findings = PerplexitySearchClient(settings).search(q)

    user_prompt = _build_user_prompt(prompt_template, payload, extracted_text)
    if web_findings:
        user_prompt += "\n\n[WEB_FINDINGS]\n" + "\n".join(
            [f"- {w.title} {w.url}\n{w.snippet}" for w in web_findings]
        )

    model_text = generate_text(settings, system_prompt="You must follow the user instructions exactly.", user_prompt=user_prompt)
    out1, out2 = _parse_two_outputs(model_text)

    return OutputPayload(
        run_id=run_id,
        mode="pricing",
        row_id=payload.row_id,
        rfq_title=payload.title,
        customer_name=payload.customer_name,
        standard=payload.standard,
        geography=payload.geography,
        industry=payload.industry,
        product_name=(payload.product.name if payload.product else ""),
        product_qty=(payload.product.qty if payload.product else ""),
        product_details=(payload.product.details if payload.product else ""),
        attachment_findings=attachment_findings,
        web_findings=web_findings,
        pricing_estimate_text=out1,
        pricing_reasoning_text=out2,
        rfq_summary_text="",
        raw_model_output=model_text,
        structured={},
    )


def run_summary(settings: Settings, payload: InputPayload) -> OutputPayload:
    run_id = uuid.uuid4().hex[:10]

    attachment_findings = analyze_attachments(settings, payload.all_attachment_urls())
    extracted_text = _join_attachment_text(payload, attachment_findings)

    prompt_template = load_prompt_file(settings.prompt_summary_file)

    # Web search is required (pricing + standards context)
    web_findings: List[WebFinding] = []
    q = f"India manufacturing cost proxy pricing for: {payload.title} | {payload.standard} | {payload.product.details if payload.product else ''}"
    web_findings = PerplexitySearchClient(settings).search(q)

    user_prompt = _build_user_prompt(prompt_template, payload, extracted_text)
    if web_findings:
        user_prompt += "\n\n[WEB_FINDINGS]\n" + "\n".join(
            [f"- {w.title} {w.url}\n{w.snippet}" for w in web_findings]
        )

    model_text = generate_text(settings, system_prompt="You must follow the user instructions exactly.", user_prompt=user_prompt)
    out1, out2 = _parse_two_outputs(model_text)

    # In summary prompt:
    # OUTPUT 1 = pricing estimate
    # OUTPUT 2 = strategic briefing & nudges  -> treat as RFQ Summary writeback
    return OutputPayload(
        run_id=run_id,
        mode="summary",
        row_id=payload.row_id,
        rfq_title=payload.title,
        customer_name=payload.customer_name,
        standard=payload.standard,
        geography=payload.geography,
        industry=payload.industry,
        product_name=(payload.product.name if payload.product else ""),
        product_qty=(payload.product.qty if payload.product else ""),
        product_details=(payload.product.details if payload.product else ""),
        attachment_findings=attachment_findings,
        web_findings=web_findings,
        pricing_estimate_text=out1,
        pricing_reasoning_text="",  # optional: keep empty; we’ll write out2 to summary column
        rfq_summary_text=out2,
        raw_model_output=model_text,
        structured={},
    )