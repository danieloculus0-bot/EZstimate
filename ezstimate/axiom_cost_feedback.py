"""Stage Axiom's reconciled actual invoice costs for human-reviewed EZstimate memory.

Separate source facts from purchase-price memory. Nothing here changes quote
arithmetic or supplier offers without explicit local adoption.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json

from .pricing import _connect, _day, _number, _required_text, _now, PRICE_UNITS

_SCHEMA = """
CREATE TABLE IF NOT EXISTS axiom_actual_cost_inbox (
 source_key TEXT PRIMARY KEY,
 content_sha256 TEXT NOT NULL,
 observation_json TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending'
     CHECK(status IN ('pending','adopted')),
 reviewed_by TEXT,
 reviewed_utc TEXT
);
"""


def _canonical(observation):
    if not isinstance(observation,dict):
        raise ValueError("Actual-cost observation must be an object")
    if observation.get("source")!="Axiom.vendor_invoice_reconciliation":
        raise ValueError("Only reconciled Axiom vendor invoice source is supported")
    if observation.get("price_memory_status")!="review_required":
        raise ValueError("Actual-cost input must explicitly require price review")
    lid=observation.get("invoice_line_id")
    if isinstance(lid,bool) or not isinstance(lid,int) or lid<1:
        raise ValueError("Invoice line ID must be positive integer")
    name=_required_text(observation,"material_key").upper()
    supplier=_required_text(observation,"supplier")
    unit=_required_text(observation,"unit").lower()
    if unit not in PRICE_UNITS:
        raise ValueError("Invoice unit is unsupported")
    if observation.get("currency")!="USD":
        raise ValueError("Cannot silently convert currency")
    day=_day(observation.get("invoice_date"),"invoice_date")
    number=_required_text(observation,"invoice_number")
    qty=_number({"quantity":observation.get("invoiced_qty")},"quantity",positive=True)
    price=_number({"unit_price":observation.get("invoiced_unit_price")},"unit_price",positive=True)
    landed=_number({"landed":observation.get("landed_unit_cost")},"landed",positive=True)
    if landed < price:
        raise ValueError("Landed price cannot be lower than material unit price in this feed")
    # These costs must have a documented original PO unit-price comparison.
    po=_number({"po":observation.get("purchase_order_unit_price")},"po",positive=True)
    if po is None:
        raise ValueError("Axiom PO baseline required")
    if _required_text(observation,"source_ref",maxlen=250)=="":  # defensive
        raise ValueError("Invoice source reference is required")
    return {
        "source":"Axiom.vendor_invoice_reconciliation",
        "price_memory_status":"review_required",
        "source_key":f"AXIOM-INVOICE-LINE-{lid}",
        "invoice_line_id":lid,
        "material_key":name,"supplier":supplier,"unit":unit,
        "currency":"USD","invoice_date":day,"invoice_number":number,
        "quantity":str(qty),"unit_price":str(price),"landed_unit_cost":str(landed),
        "po_unit_price":str(po),
        "source_ref":observation["source_ref"].strip(),
        "document_sha256":observation.get("document_sha256")
    }


def stage_axiom_cost_feedback(feed, *, path=None):
    if not isinstance(feed,dict) or feed.get("schema")!="axiom.actual_material_cost_feedback.v1":
        raise ValueError("Unsupported Axiom cost feedback schema")
    observations=feed.get("observations")
    if not isinstance(observations,list) or len(observations)>300:
        raise ValueError("Expected a bounded list of observations")
    normalized=[_canonical(x) for x in observations]
    if len({x["source_key"] for x in normalized})!=len(normalized):
        raise ValueError("Duplicate invoice line ID in source feed")
    staged=0
    with _connect(path) as con:
        con.executescript(_SCHEMA)
        for obs in normalized:
            raw=json.dumps(obs,sort_keys=True,separators=(",",":"))
            digest=hashlib.sha256(raw.encode()).hexdigest()
            prev=con.execute("SELECT * FROM axiom_actual_cost_inbox WHERE source_key=?",
                             (obs["source_key"],)).fetchone()
            if prev:
                if prev["content_sha256"]!=digest:
                    raise ValueError("Axiom invoice line previously staged with different evidence")
                continue
            con.execute("""INSERT INTO axiom_actual_cost_inbox
                           (source_key,content_sha256,observation_json)
                           VALUES(?,?,?)""",(obs["source_key"],digest,raw))
            staged+=1
    return {"staged":staged,"total":len(normalized),"status":"pending_review"}


def actual_cost_inbox(*, path=None):
    with _connect(path) as con:
        con.executescript(_SCHEMA)
        return [dict(r) for r in con.execute("""SELECT source_key,status,reviewed_by,reviewed_utc,
                        observation_json FROM axiom_actual_cost_inbox ORDER BY source_key""")]


def adopt_axiom_cost(source_key, reviewer, *, path=None):
    """Local explicit review decision, persisting the MATERIAL unit price only.

    Landed pricing is trace metadata and must not silently replace raw material
    base costs in quote calculations.
    """
    if not isinstance(source_key,str) or not source_key.startswith("AXIOM-INVOICE-LINE-"):
        raise ValueError("Valid Axiom invoice evidence key required")
    if not isinstance(reviewer,str) or not 1<=len(reviewer.strip())<=120:
        raise ValueError("Reviewer required")
    with _connect(path) as con:
        con.executescript(_SCHEMA)
        con.execute("BEGIN IMMEDIATE")
        row=con.execute("SELECT * FROM axiom_actual_cost_inbox WHERE source_key=?",
                        (source_key,)).fetchone()
        if row is None:
            raise ValueError("Unknown staged Axiom actual-cost observation")
        obs=json.loads(row["observation_json"])
        digest=hashlib.sha256(json.dumps(obs,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        if digest!=row["content_sha256"]:
            raise ValueError("Stored source cost observation failed checksum")
        if row["status"]=="adopted":
            return {"source_key":source_key,"new":False,"status":"adopted"}
        key=(obs["material_key"],obs["supplier"],"invoice",obs["source_key"],
             obs["invoice_date"],obs["unit"],obs["quantity"])
        previous=con.execute("""SELECT * FROM purchase_prices
            WHERE material_key=? AND supplier=? AND source_type=? AND source_ref=?
              AND effective_date=? AND price_unit=? AND quantity=?""",key).fetchone()
        if previous:
            if previous["unit_price"]!=obs["unit_price"] or previous["currency"]!="USD":
                raise ValueError("Adoption conflicts with existing price-memory evidence")
        else:
            notes=("Axiom invoice "+obs["invoice_number"]+
                   "; landed USD/unit "+obs["landed_unit_cost"]+
                   "; agreed PO USD/unit "+obs["po_unit_price"]+
                   "; source "+obs["source_ref"])
            con.execute("""INSERT INTO purchase_prices
                (material_key,supplier,source_type,source_ref,effective_date,
                 unit_price,price_unit,quantity,currency,notes,created_utc)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (*key[:4],key[4],obs["unit_price"],obs["unit"],obs["quantity"],
                 "USD",notes[:1000],_now()))
        con.execute("""UPDATE axiom_actual_cost_inbox
                       SET status='adopted',reviewed_by=?,reviewed_utc=?
                       WHERE source_key=?""",(reviewer.strip(),_now(),source_key))
    return {"source_key":source_key,"new":True,"status":"adopted"}
