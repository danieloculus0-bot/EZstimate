"""Persistent purchase requisitions, explicit approval, and auditable dispatch.

An approved purchase REQUEST is not a supplier purchase ORDER. The sender never
asserts an ERP created a requisition without a provider acknowledgement.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import os
import re
import uuid

from .pricing import _connect, _now, _required_text, PRICE_UNITS

STATE_TERMINAL = {"exported", "endpoint_delivered", "delivery_unknown"}


def _init(db):
    db.executescript("""
       CREATE TABLE IF NOT EXISTS purchase_requests (
          request_id TEXT PRIMARY KEY,
          client_key TEXT UNIQUE,
          payload_json TEXT NOT NULL,
          payload_sha256 TEXT NOT NULL,
          status TEXT NOT NULL,
          created_utc TEXT NOT NULL,
          approved_by TEXT,
          approved_utc TEXT,
          approval_sha256 TEXT,
          dispatch_mode TEXT,
          delivery_receipt_json TEXT,
          last_error TEXT
       );
       CREATE TABLE IF NOT EXISTS purchase_request_events (
          event_id INTEGER PRIMARY KEY AUTOINCREMENT,
          request_id TEXT NOT NULL,
          event_type TEXT NOT NULL,
          at_utc TEXT NOT NULL,
          detail_json TEXT NOT NULL
       );
       CREATE INDEX IF NOT EXISTS purchase_request_event_by_id
          ON purchase_request_events(request_id, event_id);
    """)


def _sha(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _text(value, name, limit=200, required=True):
    if not isinstance(value, str):
        raise ValueError(name + " must be text")
    result = value.strip()
    if (required and not result) or len(result) > limit:
        raise ValueError(name + " is missing or exceeds maximum length")
    return result


def _number(value, field):
    try:
        if isinstance(value, bool):
            raise ValueError()
        n = Decimal(str(value))
        if not n.is_finite() or n <= 0:
            raise ValueError()
        return str(n.normalize())
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(field + " must be a positive finite number") from None


def _day(value):
    if value in (None, ""):
        return None
    try:
        d = date.fromisoformat(value)
        if d.isoformat() != value:
            raise ValueError()
        return d.isoformat()
    except (ValueError, TypeError):
        raise ValueError("needed_by must be YYYY-MM-DD") from None


def normalize_request(body):
    if not isinstance(body, dict):
        raise ValueError("Purchase request must be an object")
    lines = body.get("lines")
    if not isinstance(lines, list) or not 1 <= len(lines) <= 100:
        raise ValueError("Supply 1 to 100 material request lines")
    items = []
    for i, line in enumerate(lines, 1):
        if not isinstance(line, dict):
            raise ValueError(f"Line {i} must be an object")
        material = _text(line.get("material_key"), f"Line {i} material_key", 200).upper()
        unit = _text(line.get("unit"), f"Line {i} unit", 20).lower()
        if unit not in PRICE_UNITS:
            raise ValueError(f"Line {i} has unsupported unit")
        item = {
            "material_key": material,
            "description": _text(line.get("description",""),"description",400,False),
            "quantity": _number(line.get("quantity"),f"Line {i} quantity"),
            "unit": unit,
            "needed_by": _day(line.get("needed_by")),
            "job": _text(line.get("job",""),"job",100,False),
            "supplier_preference": _text(line.get("supplier_preference",""),"supplier_preference",200,False),
            "source_ref": _text(line.get("source_ref",""),"source_ref",220,False),
        }
        items.append(item)
    return {
        "schema": "axiom.purchase_request.v1",
        "requested_by": _text(body.get("requested_by"),"requested_by",120),
        "department": _text(body.get("department",""),"department",100,False),
        "justification": _text(body.get("justification"),"justification",800),
        "source_system": _text(body.get("source_system","EZstimate"),"source_system",80),
        "lines":items
    }


def _event(db, request_id, event_type, detail):
    db.execute("""INSERT INTO purchase_request_events
                   (request_id, event_type, at_utc, detail_json) VALUES(?,?,?,?)""",
               (request_id, event_type, _now(), json.dumps(detail,sort_keys=True)))


def _public(row):
    if row is None:
        raise ValueError("Unknown purchase request")
    record = dict(row)
    record["payload"] = json.loads(record.pop("payload_json"))
    record["delivery_receipt"] = json.loads(record.pop("delivery_receipt_json")) if record.get("delivery_receipt_json") else None
    return record


def create_request(body, path=None):
    payload=normalize_request(body)
    digest=_sha(payload)
    client_key=body.get("client_key")
    if client_key is not None:
        client_key=_text(client_key,"client_key",120)
    request_id = "PR-" + uuid.uuid4().hex[:16].upper()
    with _connect(path) as db:
        _init(db)
        db.execute("BEGIN IMMEDIATE")
        if client_key:
            row=db.execute("SELECT * FROM purchase_requests WHERE client_key=?", (client_key,)).fetchone()
            if row:
                if row["payload_sha256"]!=digest:
                    raise ValueError("client_key already used with different request content")
                return {"request":_public(row),"new":False}
        db.execute("""INSERT INTO purchase_requests
           (request_id,client_key,payload_json,payload_sha256,status,created_utc)
           VALUES(?,?,?,?,?,?)""",
           (request_id,client_key,json.dumps(payload,sort_keys=True),digest,"draft",_now()))
        _event(db,request_id,"created",{"payload_sha256":digest})
        record=db.execute("SELECT * FROM purchase_requests WHERE request_id=?", (request_id,)).fetchone()
    return {"request":_public(record),"new":True}


def get_request(request_id,path=None):
    with _connect(path) as db:
        _init(db)
        row=db.execute("SELECT * FROM purchase_requests WHERE request_id=?", (request_id,)).fetchone()
        if not row:
            raise ValueError("Unknown purchase request")
        events=[{"event_id":e["event_id"],"event_type":e["event_type"],
                 "at_utc":e["at_utc"],"detail":json.loads(e["detail_json"])}
                for e in db.execute("SELECT * FROM purchase_request_events WHERE request_id=? ORDER BY event_id",
                                    (request_id,))]
    return {"request":_public(row),"events":events}


def recent_requests(limit=25,path=None):
    if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=100:
        raise ValueError("limit must be 1 to 100")
    with _connect(path) as db:
        _init(db)
        rows=[_public(r) for r in db.execute(
            "SELECT * FROM purchase_requests ORDER BY created_utc DESC LIMIT ?",(limit,))]
    return {"requests":rows}


def _require_approver(token):
    secret=os.environ.get("EZSTIMATE_APPROVAL_TOKEN","")
    if not secret:
        raise PermissionError("Approval token is not configured on the local server")
    if not isinstance(token,str) or not hmac.compare_digest(secret, token):
        raise PermissionError("Approval token not accepted")


def approve_request(request_id, approver, token, *, path=None):
    _require_approver(token)
    name=_text(approver,"approver",120)
    with _connect(path) as db:
        _init(db)
        db.execute("BEGIN IMMEDIATE")
        row=db.execute("SELECT * FROM purchase_requests WHERE request_id=?",(request_id,)).fetchone()
        if not row:
            raise ValueError("Unknown purchase request")
        if row["status"]!="draft":
            raise ValueError("Only a draft purchase request can be approved")
        payload=json.loads(row["payload_json"])
        if _sha(payload)!=row["payload_sha256"]:
            raise ValueError("Request source digest mismatch")
        at=_now()
        stamp=_sha({"request":request_id,"payload_sha256":row["payload_sha256"],
                    "approved_by":name,"approved_utc":at})
        db.execute("""UPDATE purchase_requests SET status='approved',approved_by=?,
                      approved_utc=?,approval_sha256=? WHERE request_id=?""",
                   (name,at,stamp,request_id))
        _event(db,request_id,"approved",{"approver":name,"payload_sha256":row["payload_sha256"],
                                         "approval_sha256":stamp})
        record=db.execute("SELECT * FROM purchase_requests WHERE request_id=?",(request_id,)).fetchone()
    return _public(record)


def dispatch_request(request_id,token,*,path=None,adapter=None):
    """Delivery runs only after a recorded approval and with the approval credential.

    The same approved immutable digest and request ID are sent on every attempt.
    Ambiguous network outcomes are never automatically retried.
    """
    _require_approver(token)
    from .erp_adapters import adapter_from_environment, DispatchError
    impl=adapter or adapter_from_environment()
    with _connect(path) as db:
        _init(db)
        db.execute("BEGIN IMMEDIATE")
        row=db.execute("SELECT * FROM purchase_requests WHERE request_id=?",(request_id,)).fetchone()
        if not row:
            raise ValueError("Unknown purchase request")
        if row["status"] in ("endpoint_delivered","exported"):
            return {"request":_public(row),"duplicate":True}
        if row["status"]!="approved":
            raise ValueError("Request is not approved for dispatch or its outcome must be reconciled")
        payload=json.loads(row["payload_json"])
        if _sha(payload)!=row["payload_sha256"] or not row["approval_sha256"]:
            raise ValueError("Approved content digest mismatch")
        db.execute("UPDATE purchase_requests SET status='dispatching',dispatch_mode=?,last_error=NULL WHERE request_id=?",
                   (impl.mode,request_id))
        _event(db,request_id,"dispatch_started",{"mode":impl.mode,"payload_sha256":row["payload_sha256"]})
    try:
        receipt=impl.deliver({"request_id":request_id,
                              "approval":{"approved_by":row["approved_by"],
                                          "approved_utc":row["approved_utc"],
                                          "approval_sha256":row["approval_sha256"]},
                              "payload":payload,"payload_sha256":row["payload_sha256"]})
        status="exported" if impl.mode=="outbox" else "endpoint_delivered"
    except DispatchError as exc:
        # The endpoint may have processed a request even if our connection timed out.
        state="delivery_unknown" if exc.uncertain else "approved"
        with _connect(path) as db:
            _init(db)
            db.execute("UPDATE purchase_requests SET status=?,last_error=? WHERE request_id=?",
                       (state,str(exc)[:350],request_id))
            _event(db,request_id,"dispatch_failed",{"state":state,"error":str(exc)[:350]})
        raise
    with _connect(path) as db:
        _init(db)
        db.execute("""UPDATE purchase_requests SET status=?,delivery_receipt_json=?,
                     last_error=NULL WHERE request_id=?""",
                   (status,json.dumps(receipt,sort_keys=True),request_id))
        _event(db,request_id,"dispatched",{"status":status,"receipt":receipt})
        row=db.execute("SELECT * FROM purchase_requests WHERE request_id=?",(request_id,)).fetchone()
    return {"request":_public(row),"duplicate":False}


def approve_and_dispatch(request_id,approver,token,*,path=None):
    approval=approve_request(request_id,approver,token,path=path)
    # Without configured transport, preserve approval so it can be sent later.
    if not os.environ.get("EZSTIMATE_ERP_MODE"):
        return {"request":approval,"delivery":None,
                "message":"Approved; configure an ERP adapter before dispatch"}
    try:
        result=dispatch_request(request_id,token,path=path)
        return {"request":result["request"],"delivery":result["request"]["delivery_receipt"],
                "message":"Approved and dispatched"}
    except Exception as exc:
        # Approval remains persisted even when external delivery fails.
        return {"request":get_request(request_id,path=path)["request"],
                "delivery":None,"message":"Approved, but dispatch did not complete: "+type(exc).__name__}
