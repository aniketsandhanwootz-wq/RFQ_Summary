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
        # dedupe, preserve order
        seen = set()
        out = []
        for u in urls:
            u2 = (u or "").strip()
            if u2 and u2 not in seen:
                seen.add(u2)
                out.append(u2)
        return out


class InputPayload(BaseModel):
    title: str = Field(alias="Title")
    industry: str = Field(default="", alias="Industry")
    geography: str = Field(default="", alias="Geography")
    standard: str = Field(default="", alias="Standard")
    customer_name: str = Field(default="", alias="Customer name")

    # comes as a JSON-string in your examples
    product_json: str = Field(default="{}", alias="Product_json")

    # optional: extra prompt override
    prompt: Optional[str] = None

    # optional: allow explicit switch
    enable_web_search: bool = False

    product: Optional[ProductItem] = None

    @model_validator(mode="after")
    def parse_product_json(self) -> "InputPayload":
        raw = (self.product_json or "").strip()
        if not raw:
            self.product = None
            return self
        try:
            obj = json.loads(raw)
        except Exception as e:
            raise ValueError(f"Product_json is not valid JSON string: {e}") from e
        # normalize keys to match ProductItem aliases
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
        if not self.product:
            return []
        return self.product.all_attachment_urls


class WebFinding(BaseModel):
    title: str
    url: str
    snippet: str = ""


class AttachmentFinding(BaseModel):
    url: str
    kind: str  # pdf|image|excel|unknown|folder
    summary: str
    # optional structured payload
    data: Dict[str, Any] = Field(default_factory=dict)


class OutputPayload(BaseModel):
    rfq_title: str
    customer_name: str = ""
    standard: str = ""
    geography: str = ""
    industry: str = ""

    product_name: str = ""
    product_qty: str = ""
    product_details: str = ""

    # what we used
    attachment_findings: List[AttachmentFinding] = Field(default_factory=list)
    web_findings: List[WebFinding] = Field(default_factory=list)

    # final answer
    summary_md: str
    structured: Dict[str, Any] = Field(default_factory=dict)

    # bookkeeping
    run_id: str