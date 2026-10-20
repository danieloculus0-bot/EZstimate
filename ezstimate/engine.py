"""Read manufacturing PDF/CSV/XLSX inputs and compute deterministic draft prices.

Fields are proposed with source references, not certified as accurate. Unknown
cost is missing, never silently zero. There is no LLM arithmetic.
"""
from __future__ import annotations
import csv
import io
import re
from pathlib import Path
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

GRADES = (
    ("ASTM A36", r"\b(?:ASTM\s*)?A[\s-]?36\b"),
    ("ASTM A572 Grade 50", r"\bA572(?:\s*GR(?:ADE)?\.?\s*50)?\b"),
    ("1018 steel", r"\b(?:AISI\s*)?1018\b"),
    ("304 stainless", r"\b(?:304\s*(?:SS|STAINLESS)|(?:SS|STAINLESS)\s*304)\b"),
    ("316 stainless", r"\b(?:316\s*(?:SS|STAINLESS)|(?:SS|STAINLESS)\s*316)\b"),
    ("5052-H32 aluminum", r"\b5052\s*[- ]?\s*H32\b"),
    ("6061-T6 aluminum", r"\b6061\s*[- ]?\s*T6\b"),
    ("HRPO", r"\bHRPO\b"),
    ("CRS", r"\bCRS\b"),
)
FIELDS = {
    "part_number": r"\b(?:PART\s*(?:NO\.?|NUMBER|#)|DRAWING\s*(?:NO\.?|NUMBER|#)|DWG\s*(?:NO\.?|#))\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{2,})",
    "revision": r"\bREV(?:ISION)?\s*[:#-]?\s*([A-Z0-9]{1,4})\b",
    "quantity": r"\b(?:QTY|QUANTITY)\s*[:#-]?\s*(\d{1,8})\b",
    "po_number": r"\b(?:PURCHASE\s*ORDER|P\.?O\.?)\s*(?:NO\.?|NUMBER|#|:)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9/-]{2,})",
    "payment_terms": r"\b(?:NET\s*(?:15|30|45|60|90)|DUE\s+ON\s+RECEIPT|PREPAID)\b",
    "shipping_terms": r"\b(?:FOB\s+(?:ORIGIN|DESTINATION|PREPAID)|EXW\b|DAP\b|DDP\b)",
    "required_date": r"\b(?:REQUIRED\s*(?:BY|DATE)|DELIVER\s*BY|SHIP\s*BY|DUE\s*DATE)\s*[:#]?\s*(\d{1,4}[/-]\d{1,2}[/-]\d{2,4})\b",
    "po_unit_price": r"\b(?:UNIT\s*PRICE|PRICE\s*/\s*EA)\s*[:$ ]+\s*(\d+(?:\.\d{2})?)\b",
    "po_total": r"\b(?:PO\s*TOTAL|ORDER\s*TOTAL)\s*[:$ ]+\s*(\d+(?:\.\d{2})?)\b",
}
PROCESSES = {
    "cutting": r"\b(?:LASER|PLASMA|WATERJET)\b",
    "forming": r"\b(?:FORM|BEND|BRAKE)\b",
    "welding": r"\b(?:WELD|GMAW|GTAW|MIG|TIG)\b",
    "machining": r"\b(?:MACHINE|MILL|DRILL|REAM|TAP)\b",
    "powder coating": r"\bPOWDER\s*(?:COAT|FINISH)\b",
}
def ev(value, source, page=None, region=None, row=None):
    return {"value": str(value).strip(), "source": source, "page": page,
            "region": region, "row": row, "status": "proposed", "needs_review": True}

def candidate(pattern, regions, source):
    for region in regions:
        m = re.search(pattern, region["text"], re.I | re.M)
        if m:
            return ev(m.group(1) if m.lastindex else m.group(0),
                      source, region.get("page"), region.get("region"))
    return None

def read_material(regions, source):
    for region in regions:
        lines = region["text"].splitlines()
        for n, line in enumerate(lines):
            m = re.match(r"^\s*MATERIAL\s*[:\-]\s*(.+)$", line, re.I)
            raw = m.group(1).strip() if m else ""
            if not raw and re.fullmatch(r"\s*MATERIAL\s*[:\-]?\s*", line, re.I) and n+1 < len(lines):
                raw = lines[n+1].strip()
            if 1 < len(raw) <= 80:
                return ev(raw, source, region.get("page"), region.get("region"))
    for region in regions:
        for grade, pattern in GRADES:
            if re.search(pattern, region["text"], re.I):
                return ev(grade, source, region.get("page"), region.get("region"))
    return None

def bom_table(rows, source, page=None, sheet=None):
    if not rows:
        return []
    labels = [re.sub(r"[^a-z0-9]", "", str(v or "").lower()) for v in rows[0]]
    aliases = {"part_number": ("partnumber", "partno", "part", "itemnumber", "itemno"),
               "quantity": ("qty", "quantity", "count"),
               "description": ("description", "desc", "name"),
               "material": ("material", "grade"),
               "revision": ("revision", "rev")}
    positions = {k: next((i for i, val in enumerate(labels) if val in aliases[k]), None)
                 for k in aliases}
    if positions["part_number"] is None or positions["quantity"] is None:
        return []
    result = []
    for row_id, values in enumerate(rows[1:], 2):
        def cell(field):
            index = positions[field]
            return str(values[index] if index is not None and index < len(values) and values[index] is not None else "").strip()
        part, count = cell("part_number"), cell("quantity")
        if not part:
            continue
        try:
            qty = Decimal(count)
            if qty <= 0 or qty != qty.to_integral_value():
                continue
        except InvalidOperation:
            continue
        result.append({"part_number": part, "quantity": int(qty),
                       "description": cell("description"), "material": cell("material"),
                       "revision": cell("revision"), "source": source, "page": page,
                       "sheet": sheet, "row": row_id, "status": "proposed",
                       "needs_review": True})
    return result

def inspect_document(filename, content):
    name = Path(filename).name
    ext = Path(name).suffix.lower()
    if len(content) > 15_000_000:
        raise ValueError("File exceeds 15 MB")
    if ext in (".csv", ".xlsx"):
        if ext == ".csv":
            rows = [(None, list(csv.reader(io.StringIO(content.decode("utf-8-sig")))))]
        else:
            from openpyxl import load_workbook
            with io.BytesIO(content) as stream:
                wb = load_workbook(stream, read_only=True, data_only=True)
                try:
                    rows = [(sheet.title, list(sheet.values)) for sheet in wb]
                finally:
                    wb.close()
        bom = [item for sheet, rowset in rows for item in bom_table(rowset, name, sheet=sheet)]
        return {"filename": name, "kind": "bom", "fields": {}, "bom": bom, "process_hints": [],
                "warnings": [] if bom else ["No recognizable BOM part and quantity headers"]}
    if ext != ".pdf":
        raise ValueError("Supported files: PDF, CSV and XLSX")
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF must be installed") from exc
    regions, text, bom = [], [], []
    with fitz.open(stream=content, filetype="pdf") as pdf:
        if pdf.is_encrypted or len(pdf) > 100:
            raise ValueError("Supply unlocked PDFs with 100 pages or fewer")
        for n, page in enumerate(pdf, 1):
            rect = page.rect
            crop = fitz.Rect(rect.x0+rect.width*.48, rect.y0+rect.height*.62, rect.x1, rect.y1)
            regions.append({"text": page.get_text("text", clip=crop, sort=True),
                            "page": n, "region": "lower-right title block"})
            whole = page.get_text("text", sort=True)
            text.append(whole)
            regions.append({"text": whole, "page": n, "region": "full page"})
            if hasattr(page, "find_tables"):
                try:
                    for tab in page.find_tables().tables:
                        bom += bom_table(tab.extract(), name, page=n)
                except (AttributeError, ValueError):
                    pass
    joined = "\n".join(text)
    kind = "purchase_order" if re.search(r"\bPURCHASE\s+ORDER\b|\bP\.?O\.?\s*(?:NO|NUMBER|#)", joined, re.I) else "drawing"
    fields = {}
    for key, pat in FIELDS.items():
        if (key.startswith("po_") or key.endswith("_terms") or key == "required_date") and kind != "purchase_order":
            continue
        val = candidate(pat, regions, name)
        if val:
            fields[key] = val
    mat = read_material(regions, name)
    if mat:
        fields["material"] = mat
    hints = []
    for label, pat in PROCESSES.items():
        val = candidate(pat, regions, name)
        if val:
            val["value"] = label
            hints.append(val)
    warnings = []
    if not joined.strip():
        warnings.append("PDF has no extractable text; scanned OCR not implemented")
    if not mat and kind == "drawing":
        warnings.append("Material unidentified; verify grade and stock form")
    if not bom:
        warnings.append("No structured PDF BOM found; add lines or import spreadsheet")
    return {"filename": name, "kind": kind, "fields": fields,
            "bom": bom, "process_hints": hints, "warnings": warnings}

def review_package(documents):
    issues = []
    for key in ("part_number", "revision", "quantity", "material"):
        fields = [d["fields"][key] for d in documents if key in d.get("fields", {})]
        if len({item["value"].casefold() for item in fields}) > 1:
            issues.append({"field": key, "severity": "review",
                           "message": "Conflicting " + key.replace("_", " ") + " candidates",
                           "sources": [item["source"] for item in fields]})
    # PO quantity mismatch is meaningful only when an identical part is
    # present in a supplied BOM. Assembly subcomponents are not compared.
    for po in (d for d in documents if d.get("kind") == "purchase_order"):
        fields = po.get("fields", {})
        if "part_number" not in fields or "quantity" not in fields:
            continue
        part = fields["part_number"]["value"].casefold()
        for doc in documents:
            if doc is po:
                continue
            for row in doc.get("bom", []):
                if row.get("part_number", "").casefold() == part:
                    try:
                        po_qty = int(fields["quantity"]["value"])
                        if po_qty != int(row["quantity"]):
                            issues.append({"field": "quantity", "severity": "review",
                                "message": "PO quantity differs from BOM for matching part " + row["part_number"],
                                "sources": [po["filename"], doc["filename"]]})
                    except (ValueError, TypeError):
                        pass
    for doc in documents:
        for note in doc.get("warnings", []):
            issues.append({"field": "document", "severity": "review",
                           "message": note, "sources": [doc["filename"]]})
    return issues

def num(raw, label, required=True):
    if raw in (None, ""):
        if required:
            raise ValueError(label + " missing")
        return Decimal(0)
    try:
        value = Decimal(str(raw))
    except InvalidOperation as exc:
        raise ValueError(label + " invalid") from exc
    if not value.is_finite() or value < 0:
        raise ValueError(label + " must be finite and nonnegative")
    return value

def money(value):
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

def price_quote(payload):
    lines = payload.get("lines", []) if isinstance(payload, dict) else []
    if not isinstance(lines, list) or not lines:
        return {"status": "incomplete", "lines": [], "issues": ["No quote lines provided"], "total": None}
    out, issues, total = [], [], Decimal(0)
    for n, line in enumerate(lines, 1):
        part = str(line.get("part_number") or "(unnamed)")
        try:
            qty = num(line.get("quantity"), "quantity")
            if qty <= 0 or qty != qty.to_integral_value():
                raise ValueError("quantity must be a positive integer")
            material = num(line.get("material_cost_each"), "material cost")
            hours = num(line.get("labor_hours_each"), "labor hours")
            rate = num(line.get("shop_rate_per_hour"), "shop rate") if hours else Decimal(0)
            outside = num(line.get("outside_cost_each"), "outside cost", False)
            setup = num(line.get("setup_cost_total"), "setup cost", False)
            scrap = num(line.get("scrap_pct"), "scrap percent", False)
            margin = num(line.get("margin_pct"), "margin percent", False)
            if scrap > 100 or margin >= 100:
                raise ValueError("scrap must be 0..100%, margin must be under 100%")
            cost = (material*(1+scrap/100)+hours*rate+outside)*qty + setup
            sell = cost/(1-margin/100)
            total += sell
            out.append({"part_number": part, "quantity": int(qty),
                        "manufacturing_cost": money(cost), "unit_sell": money(sell/qty),
                        "extended_sell": money(sell), "source": line.get("source"),
                        "status": "draft"})
        except (ValueError, TypeError) as exc:
            issues.append("Line " + str(n) + " (" + part + "): " + str(exc))
            out.append({"part_number": part, "extended_sell": None, "status": "incomplete"})
    return {"status": "draft_review" if not issues else "incomplete",
            "lines": out, "issues": issues, "total": money(total) if not issues else None,
            "currency": "USD", "tax": None, "freight": None, "approval": "not approved",
            "notes": ["Explicit cost inputs only", "Taxes and freight not priced",
                      "Human review required before release"]}
