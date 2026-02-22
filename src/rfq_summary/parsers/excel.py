from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, List, Tuple
import re

from openpyxl import load_workbook  # type: ignore

from ..config import Settings
from ..schema import AttachmentFinding
from .image import analyze_image_bytes


def _cell_to_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    return str(v).strip()


def _extract_sheet_matrix(ws, max_rows: int, max_cols: int) -> List[List[str]]:
    rows: List[List[str]] = []
    max_r = min(ws.max_row or 0, max_rows)
    max_c = min(ws.max_column or 0, max_cols)
    for r in range(1, max_r + 1):
        row = []
        for c in range(1, max_c + 1):
            row.append(_cell_to_str(ws.cell(r, c).value))
        rows.append(row)
    return rows


def _detect_table_regions(rows: List[List[str]], max_tables: int) -> List[Dict[str, Any]]:
    """
    Better heuristic:
    - header row: >=2 non-empty and looks like labels (short strings)
    - table continues until empty separator row
    """
    tables = []
    r = 0
    n = len(rows)

    def looks_like_header(row: List[str]) -> bool:
        non_empty = [c for c in row if c]
        if len(non_empty) < 2:
            return False
        # header cells usually shorter
        short = sum(1 for c in non_empty if len(c) <= 30)
        return short >= max(2, int(0.6 * len(non_empty)))

    def trim_right(rr: List[str]) -> List[str]:
        last = -1
        for i, c in enumerate(rr):
            if c:
                last = i
        return rr[: last + 1] if last >= 0 else []

    while r < n and len(tables) < max_tables:
        row = rows[r]
        if looks_like_header(row):
            header = trim_right(row)
            body = []
            r2 = r + 1
            while r2 < n:
                row2 = rows[r2]
                ne2 = sum(1 for c in row2 if c)
                if ne2 == 0:
                    break
                body.append(trim_right(row2))
                r2 += 1

            if header and body:
                tables.append(
                    {
                        "start_row": r + 1,
                        "end_row": r2,
                        "header": header[:40],
                        "rows_sample": [b[:40] for b in body[:60]],
                        "row_count_sampled": min(len(body), 60),
                    }
                )
            r = r2 + 1
        else:
            r += 1

    return tables


def _extract_nonempty_cells(ws, max_items: int = 120) -> List[Dict[str, Any]]:
    """
    Useful when table detection fails: capture key-value cells.
    """
    out = []
    count = 0
    max_r = min(ws.max_row or 0, 300)
    max_c = min(ws.max_column or 0, 50)
    for r in range(1, max_r + 1):
        for c in range(1, max_c + 1):
            v = ws.cell(r, c).value
            s = _cell_to_str(v)
            if s:
                out.append({"cell": f"{ws.cell(r, c).coordinate}", "value": s[:200]})
                count += 1
                if count >= max_items:
                    return out
    return out


def _find_formula_links(ws) -> List[Dict[str, str]]:
    """
    Extract cross-sheet references like Sheet2!A1 from formulas.
    Requires workbook loaded with data_only=False.
    """
    links = []
    max_r = min(ws.max_row or 0, 300)
    max_c = min(ws.max_column or 0, 50)

    pat = re.compile(r"([A-Za-z0-9_ ]+)!([A-Z]{1,3}\d+)")
    for r in range(1, max_r + 1):
        for c in range(1, max_c + 1):
            v = ws.cell(r, c).value
            if isinstance(v, str) and v.startswith("="):
                for m in pat.finditer(v):
                    links.append({"from_cell": ws.cell(r, c).coordinate, "to": f"{m.group(1)}!{m.group(2)}"})
                    if len(links) >= 80:
                        return links
    return links


def analyze_excel_bytes(settings: Settings, url: str, data: bytes) -> AttachmentFinding:
    # load values + formulas
    wb_vals = load_workbook(filename=BytesIO(data), data_only=True)
    wb_form = load_workbook(filename=BytesIO(data), data_only=False)

    sheet_summaries: List[Dict[str, Any]] = []
    embedded_images: List[Dict[str, Any]] = []
    relations: List[Dict[str, Any]] = []

    for ws in wb_vals.worksheets:
        matrix = _extract_sheet_matrix(ws, settings.max_excel_rows, settings.max_excel_cols)
        tables = _detect_table_regions(matrix, settings.max_excel_tables_per_sheet)
        nonempty = _extract_nonempty_cells(ws)

        sheet_summaries.append(
            {
                "sheet": ws.title,
                "tables_detected": len(tables),
                "tables": tables,
                "nonempty_cells_sample": nonempty[:60],
            }
        )

        # embedded images
        imgs = getattr(ws, "_images", None) or []
        for idx, img in enumerate(imgs[:10]):
            try:
                img_bytes = img._data()  # type: ignore[attr-defined]
                finding = analyze_image_bytes(settings, f"{url}#sheet={ws.title}&img={idx+1}", img_bytes)
                embedded_images.append(
                    {
                        "sheet": ws.title,
                        "image_index": idx + 1,
                        "summary": finding.summary,
                    }
                )
            except Exception:
                embedded_images.append(
                    {
                        "sheet": ws.title,
                        "image_index": idx + 1,
                        "summary": "Embedded image detected but could not extract bytes.",
                    }
                )

    # formula relations
    for ws in wb_form.worksheets:
        links = _find_formula_links(ws)
        if links:
            relations.append({"sheet": ws.title, "formula_links": links[:80]})

    # compact summary text
    lines = [f"Excel analyzed. Sheets: {len(sheet_summaries)}."]
    for sh in sheet_summaries[:8]:
        lines.append(f"- Sheet '{sh['sheet']}': tables={sh['tables_detected']}  nonempty_cells_sample={len(sh['nonempty_cells_sample'])}")
    if relations:
        lines.append(f"Cross-sheet formula links detected in {len(relations)} sheet(s).")
    if embedded_images:
        lines.append(f"Embedded images analyzed: {len(embedded_images)} (capped).")

    return AttachmentFinding(
        url=url,
        kind="excel",
        summary="\n".join(lines).strip(),
        data={
            "sheets": sheet_summaries,
            "relations": relations,
            "embedded_images": embedded_images,
        },
    )