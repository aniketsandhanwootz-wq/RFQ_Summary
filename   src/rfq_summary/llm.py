from __future__ import annotations

from typing import List
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from .config import Settings
from .schema import AttachmentFinding, WebFinding


SYSTEM_PROMPT = """You are an RFQ analyst.
You must prioritize attachment-derived facts over web content.
If something is missing, explicitly mark it as unknown instead of guessing.
Output must be concise, engineering-grade, and use bullets where appropriate.
"""


def build_user_prompt(
    base_prompt: str,
    rfq_title: str,
    industry: str,
    geography: str,
    standard: str,
    customer_name: str,
    product_name: str,
    product_qty: str,
    product_details: str,
    attachment_findings: List[AttachmentFinding],
    web_findings: List[WebFinding],
) -> str:
    att_block = "\n".join(
        [f"- ({a.kind}) {a.url}\n  Summary: {a.summary}" for a in attachment_findings]
    ) or "- None"

    web_block = "\n".join(
        [f"- {w.title}: {w.url}\n  {w.snippet}".strip() for w in web_findings]
    ) or "- None"

    return f"""
{base_prompt}

RFQ:
- Title: {rfq_title}
- Customer: {customer_name}
- Industry: {industry}
- Geography: {geography}
- Standard: {standard}

Product:
- Name: {product_name}
- Qty: {product_qty}
- Details: {product_details}

Attachment Findings (primary truth):
{att_block}

Web Findings (secondary, cite when used):
{web_block}

Task:
- Produce a crisp RFQ summary.
- Extract specs/dimensions/material/finish/tolerance if present.
- Highlight missing info + risks.
- If web findings are used, add a small "Web references" section listing URLs used.
""".strip()


def generate_summary_md(
    settings: Settings,
    user_prompt: str,
) -> str:
    if not settings.gemini_api_key.strip():
        raise RuntimeError("Missing GEMINI_API_KEY")

    llm = ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.gemini_api_key,
        temperature=0.2,
    )

    msgs = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]
    resp = llm.invoke(msgs)
    return (resp.content or "").strip()