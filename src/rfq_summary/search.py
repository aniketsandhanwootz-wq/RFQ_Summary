from __future__ import annotations

from dataclasses import dataclass
from typing import List

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import Settings
from .schema import WebFinding


@dataclass(frozen=True)
class PerplexitySearchClient:
    settings: Settings

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=6))
    def search(self, query: str) -> List[WebFinding]:
        key = (self.settings.perplexity_api_key or "").strip()
        if not key:
            return []

        url = self.settings.perplexity_base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

        payload = {
            "model": self.settings.perplexity_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a web researcher. Answer concisely with citations. "
                        "Prefer authoritative sources and include current pricing context when asked."
                    ),
                },
                {"role": "user", "content": query},
            ],
            "temperature": 0.2,
        }

        timeout = httpx.Timeout(connect=8.0, read=25.0, write=10.0, pool=10.0)

        with httpx.Client(timeout=timeout) as client:
            r = client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()

        text = ""
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except Exception:
            text = ""

        citations = data.get("citations") or []
        findings: List[WebFinding] = []

        if text.strip():
            findings.append(WebFinding(title="Web summary", url="", snippet=text.strip()[:5000]))

        if isinstance(citations, list) and citations:
            for c in citations[: int(self.settings.perplexity_max_results)]:
                if isinstance(c, str) and c.strip():
                    findings.append(WebFinding(title="Source", url=c.strip(), snippet=""))

        return findings