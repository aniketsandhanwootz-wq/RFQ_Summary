from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import Settings
from .schema import WebFinding


@dataclass(frozen=True)
class PerplexitySearchClient:
    settings: Settings

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    def search(self, query: str) -> List[WebFinding]:
        """
        Uses Perplexity API to perform web-grounded answering and extracts citations-ish.
        NOTE: exact response fields can vary by model/product; keep it tolerant.
        """
        key = (self.settings.perplexity_api_key or "").strip()
        if not key:
            return []

        url = self.settings.perplexity_base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.settings.perplexity_model,
            "messages": [
                {"role": "system", "content": "You are a web search engine. Return concise findings with sources."},
                {"role": "user", "content": query},
            ],
            # Keep output controlled
            "temperature": 0.2,
        }

        with httpx.Client(timeout=40) as client:
            r = client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()

        # Tolerant extraction:
        # Some responses include citations in: data["citations"] or within message metadata.
        text = ""
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except Exception:
            text = ""

        citations = data.get("citations") or []
        findings: List[WebFinding] = []

        # If citations list is present, create findings from it.
        # If not, fallback to a single finding with the text.
        if isinstance(citations, list) and citations:
            for c in citations[: self.settings.perplexity_max_results]:
                if isinstance(c, str) and c.strip():
                    findings.append(WebFinding(title="Source", url=c.strip(), snippet=""))
        else:
            # fallback: no URLs; keep text as snippet (not ideal but useful)
            findings.append(WebFinding(title="Web summary", url="", snippet=text[:2000]))

        return findings


def build_web_query(rfq_title: str, standard: str, product_details: str) -> str:
    parts = [rfq_title.strip()]
    if standard.strip():
        parts.append(f"standard {standard.strip()}")
    if product_details.strip():
        parts.append(product_details.strip())
    q = " | ".join([p for p in parts if p])
    return q