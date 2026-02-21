from __future__ import annotations

import uuid
from typing import List

from .config import Settings
from .schema import InputPayload, OutputPayload, AttachmentFinding, WebFinding
from .search import PerplexitySearchClient, build_web_query
from .llm import build_user_prompt, generate_summary_md
from .writer import write_output
from .attachments import analyze_attachments


DEFAULT_PROMPT = """You are given an RFQ JSON and attachments analysis.
Summarize requirements and extract technical specs. Do not invent values.
"""


def run_task(settings: Settings, payload: InputPayload) -> OutputPayload:
    run_id = uuid.uuid4().hex[:10]

    # 1) Attachment analysis (Part 2 will implement real logic)
    attachment_findings = analyze_attachments(settings, payload.all_attachment_urls())
    # placeholder: later -> attachments.analyze_attachments(...)

    # 2) Optional web search (Perplexity)
    web_findings: List[WebFinding] = []
    if payload.enable_web_search:
        q = build_web_query(payload.title, payload.standard, (payload.product.details if payload.product else ""))
        web_findings = PerplexitySearchClient(settings).search(q)

    # 3) LLM generation (Gemini via LangChain)
    base_prompt = payload.prompt or DEFAULT_PROMPT

    product = payload.product
    user_prompt = build_user_prompt(
        base_prompt=base_prompt,
        rfq_title=payload.title,
        industry=payload.industry,
        geography=payload.geography,
        standard=payload.standard,
        customer_name=payload.customer_name,
        product_name=(product.name if product else ""),
        product_qty=(product.qty if product else ""),
        product_details=(product.details if product else ""),
        attachment_findings=attachment_findings,
        web_findings=web_findings,
    )

    summary_md = generate_summary_md(settings, user_prompt)

    out = OutputPayload(
        rfq_title=payload.title,
        customer_name=payload.customer_name,
        standard=payload.standard,
        geography=payload.geography,
        industry=payload.industry,
        product_name=(product.name if product else ""),
        product_qty=(product.qty if product else ""),
        product_details=(product.details if product else ""),
        attachment_findings=attachment_findings,
        web_findings=web_findings,
        summary_md=summary_md,
        structured={},
        run_id=run_id,
    )

    # 4) Write output
    write_output(settings, out)
    return out