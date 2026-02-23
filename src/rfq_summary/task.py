from __future__ import annotations

import json
import uuid
from typing import Tuple, List, Optional

from .config import Settings
from .schema import InputPayload, OutputPayload, WebFinding
from .attachments import analyze_attachments
from .search import PerplexitySearchClient
from .llm import load_prompt_file, generate_text


def _join_attachment_text(payload: InputPayload, attachment_findings) -> str:
    if (payload.extracted_attachment_text or "").strip():
        return payload.extracted_attachment_text.strip()

    blocks = []
    for a in attachment_findings:
        blocks.append(f"[{a.kind}] {a.url}\n{a.summary}\n")
    return "\n".join(blocks).strip()


def _parse_two_outputs(model_text: str) -> Tuple[str, str]:
    t = model_text or ""
    i1 = t.find("=== OUTPUT 1")
    i2 = t.find("=== OUTPUT 2")
    if i1 >= 0 and i2 > i1:
        out1 = t[i1:i2].strip()
        out2 = t[i2:].strip()
        return out1, out2
    return "", t.strip()


def _parse_single_output(model_text: str) -> str:
    t = (model_text or "").strip()
    if not t:
        return ""
    idx = t.find("=== OUTPUT")
    if idx >= 0:
        return t[idx:].strip()
    return t


def _products_for_prompt(payload: InputPayload) -> List[dict]:
    out: List[dict] = []
    # NOTE: your schema must provide payload.products (multi) OR at least payload.product (single).
    # This code tolerates both.
    products = getattr(payload, "products", None)
    if products:
        for p in products:
            out.append(
                {
                    "sr_no": p.sr_no,
                    "Name": p.name,
                    "Qty": p.qty,
                    "Details": p.details,
                    "Dwg": p.dwg,
                    "photo": p.photo,
                    "files": p.files,
                }
            )
    elif payload.product:
        p = payload.product
        out.append(
            {
                "sr_no": p.sr_no,
                "Name": p.name,
                "Qty": p.qty,
                "Details": p.details,
                "Dwg": p.dwg,
                "photo": p.photo,
                "files": p.files,
            }
        )
    return out


def _build_user_prompt(prompt_template: str, payload: InputPayload, extracted_text: str) -> str:
    rfq_json = {
        "Title": payload.title,
        "Industry": payload.industry,
        "Geography": payload.geography,
        "Standard": payload.standard,
        "Customer name": payload.customer_name,
        "Product_json": payload.product_json,       # raw traceability
        "Products": _products_for_prompt(payload),  # structured for multi-product
        "rowID": payload.row_id,
    }
    return (
        prompt_template
        .replace("{{insert_main_rfq_json_here}}", json.dumps(rfq_json, ensure_ascii=False))
        .replace("{{insert_extracted_text_from_power_automate_here}}", extracted_text or "")
    )


def _compact_product_text(payload: InputPayload) -> str:
    parts: List[str] = []
    products = getattr(payload, "products", None)
    if products:
        for p in products[:8]:
            s = f"{p.name}".strip()
            if p.qty:
                s += f" | Qty: {p.qty}"
            if p.details:
                d = p.details.replace("\n", " ").strip()
                s += f" | {d[:180]}"
            if s:
                parts.append(s)
        if len(products) > 8:
            parts.append(f"...(+{len(products) - 8} more items)")
        return " || ".join(parts)

    # single product fallback
    if payload.product:
        p = payload.product
        s = f"{p.name}".strip()
        if p.qty:
            s += f" | Qty: {p.qty}"
        if p.details:
            d = p.details.replace("\n", " ").strip()
            s += f" | {d[:180]}"
        return s
    return ""


def run_pricing(settings: Settings, payload: InputPayload, run_id: Optional[str] = None) -> OutputPayload:
    run_id = run_id or uuid.uuid4().hex[:10]

    attachment_findings = analyze_attachments(settings, payload.all_attachment_urls())
    extracted_text = _join_attachment_text(payload, attachment_findings)

    prompt_template = load_prompt_file(settings.prompt_pricing_file)

    q = (
        f"Wholesale unit pricing India for RFQ: {payload.title} | {payload.standard} | "
        f"{_compact_product_text(payload)}"
    )
    web_findings: List[WebFinding] = PerplexitySearchClient(settings).search(q)

    user_prompt = _build_user_prompt(prompt_template, payload, extracted_text)
    if web_findings:
        user_prompt += "\n\n[WEB_FINDINGS]\n" + "\n".join(
            [f"- {w.title} {w.url}\n{w.snippet}" for w in web_findings]
        )

    model_text = generate_text(
        settings,
        system_prompt="You must follow the user instructions exactly.",
        user_prompt=user_prompt,
    )
    out1, out2 = _parse_two_outputs(model_text)

    first = payload.product
    products = getattr(payload, "products", None) or []
    return OutputPayload(
        run_id=run_id,
        mode="pricing",
        row_id=payload.row_id,
        rfq_title=payload.title,
        customer_name=payload.customer_name,
        standard=payload.standard,
        geography=payload.geography,
        industry=payload.industry,
        product_name=(first.name if first else (f"{len(products)} item(s)" if products else "")),
        product_qty=(first.qty if first else ""),
        product_details=(first.details if first else ""),
        attachment_findings=attachment_findings,
        web_findings=web_findings,
        pricing_estimate_text=out1,
        pricing_reasoning_text=out2,
        rfq_summary_text="",
        raw_model_output=model_text,
        structured={"products_count": (len(products) if products else (1 if first else 0))},
    )


def run_summary(settings: Settings, payload: InputPayload, run_id: Optional[str] = None) -> OutputPayload:
    run_id = run_id or uuid.uuid4().hex[:10]

    attachment_findings = analyze_attachments(settings, payload.all_attachment_urls())
    extracted_text = _join_attachment_text(payload, attachment_findings)

    prompt_template = load_prompt_file(settings.prompt_summary_file)

    q = (
        f"India supplier clusters and cost proxy guidance for RFQ: {payload.title} | {payload.standard} | "
        f"{_compact_product_text(payload)}"
    )
    web_findings: List[WebFinding] = PerplexitySearchClient(settings).search(q)

    user_prompt = _build_user_prompt(prompt_template, payload, extracted_text)
    if web_findings:
        user_prompt += "\n\n[WEB_FINDINGS]\n" + "\n".join(
            [f"- {w.title} {w.url}\n{w.snippet}" for w in web_findings]
        )

    model_text = generate_text(
        settings,
        system_prompt="You must follow the user instructions exactly.",
        user_prompt=user_prompt,
    )

    summary_out = _parse_single_output(model_text)

    first = payload.product
    products = getattr(payload, "products", None) or []
    return OutputPayload(
        run_id=run_id,
        mode="summary",
        row_id=payload.row_id,
        rfq_title=payload.title,
        customer_name=payload.customer_name,
        standard=payload.standard,
        geography=payload.geography,
        industry=payload.industry,
        product_name=(first.name if first else (f"{len(products)} item(s)" if products else "")),
        product_qty=(first.qty if first else ""),
        product_details=(first.details if first else ""),
        attachment_findings=attachment_findings,
        web_findings=web_findings,
        pricing_estimate_text="",
        pricing_reasoning_text="",
        rfq_summary_text=summary_out,
        raw_model_output=model_text,
        structured={"products_count": (len(products) if products else (1 if first else 0))},
    )