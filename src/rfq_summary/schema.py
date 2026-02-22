from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


class ProductItem(BaseModel):
    sr_no: Optional[int] = None
    name: str = Field(default="", alias="Name")
    qty: str = Field(default="", alias="Qty")
    details: str = Field(default="", alias="Details")
    dwg: Optional[str] = Field(default=None, alias="Dwg")
    photo: List[str] = Field(default_factory=list)
    files: List[str] = Field(default_factory=list)

    @property
    def all_attachment_urls(self) -> List[str]:
        urls: List[str] = []
        if self.dwg:
            urls.append(self.dwg)
        urls.extend(self.photo or [])
        urls.extend(self.files or [])
        seen = set()
        out = []
        for u in urls:
            u2 = (u or "").strip()
            if u2 and u2 not in seen:
                seen.add(u2)
                out.append(u2)
        return out


class InputPayload(BaseModel):
    # IMPORTANT: Glide rowID
    row_id: str = Field(default="", alias="rowID")  # Glide should send rowID

    title: str = Field(alias="Title")
    industry: str = Field(default="", alias="Industry")
    geography: str = Field(default="", alias="Geography")
    standard: str = Field(default="", alias="Standard")
    customer_name: str = Field(default="", alias="Customer name")

    product_json: str = Field(default="{}", alias="Product_json")

    # Optional: if you ever pass extracted text directly (Power Automate etc.)
    extracted_attachment_text: str = Field(default="", alias="Extracted Attachment Text")

    product: Optional[ProductItem] = None

    @model_validator(mode="after")
    def parse_product_json(self) -> "InputPayload":
        raw = (self.product_json or "").strip()
        if not raw:
            self.product = None
            return self
        obj = json.loads(raw)

        if "Name" not in obj and "name" in obj:
            obj["Name"] = obj["name"]
        if "Qty" not in obj and "qty" in obj:
            obj["Qty"] = obj["qty"]
        if "Details" not in obj and "details" in obj:
            obj["Details"] = obj["details"]
        if "Dwg" not in obj and "dwg" in obj:
            obj["Dwg"] = obj["dwg"]

        self.product = ProductItem.model_validate(obj)
        return self

    def all_attachment_urls(self) -> List[str]:
        return self.product.all_attachment_urls if self.product else []


class WebFinding(BaseModel):
    title: str
    url: str
    snippet: str = ""


class AttachmentFinding(BaseModel):
    url: str
    kind: str
    summary: str
    data: Dict[str, Any] = Field(default_factory=dict)


class OutputPayload(BaseModel):
    run_id: str
    mode: str  # "pricing" | "summary"
    row_id: str

    rfq_title: str
    customer_name: str = ""
    standard: str = ""
    geography: str = ""
    industry: str = ""

    product_name: str = ""
    product_qty: str = ""
    product_details: str = ""

    attachment_findings: List[AttachmentFinding] = Field(default_factory=list)
    web_findings: List[WebFinding] = Field(default_factory=list)

    # parsed LLM outputs
    pricing_estimate_text: str = ""
    pricing_reasoning_text: str = ""
    rfq_summary_text: str = ""

    raw_model_output: str = ""
    structured: Dict[str, Any] = Field(default_factory=dict)