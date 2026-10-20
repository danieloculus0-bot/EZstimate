"""Freeze material-price-pressure hypotheses before subsequent invoice outcomes.

Evaluations are deterministic, source-matched and exclude hindsight and missing invoices.
A market-pressure warning is not a price forecast in dollars or a learned policy.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json

from .pricing import _connect, _day, _now, _number, _required_text, PRICE_UNITS, market_pressure


def _init(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS forecast_snapshots (
          id INTEGER PRIMARY KEY,
          issued_date TEXT NOT NULL,
          issued_utc TEXT NOT NULL,
          material_key TEXT NOT NULL,
          material_family TEXT NOT NULL,
          supplier TEXT NOT NULL,
          price_unit TEXT NOT NULL,
          quantity TEXT NOT NULL,
          horizon_days INTEGER NOT NULL,
          spike_threshold_pct TEXT NOT NULL,
          baseline_price_id INTEGER NOT NULL,
          baseline_price TEXT NOT NULL,
          baseline_source_ref TEXT NOT NULL,
          risk TEXT NOT NULL,
          pressure_score INTEGER NOT NULL,
          signal_evidence_json TEXT NOT NULL,
          UNIQUE(issued_date, material_key, supplier, price_unit, quantity, horizon_days)
        );
        CREATE INDEX IF NOT EXISTS forecast_date_lookup ON forecast_snapshots(issued_date);
    """)


def freeze_forecast(payload, *, path=None, issue_date=None):
    """Issue as of today in production. issue_date exists only for deterministic tests."""
    if not isinstance(payload, dict):
        raise ValueError("Forecast must be an object")
    material = _required_text(payload, "material_key").upper()
    supplier = _required_text(payload, "supplier")
    unit = _required_text(payload, "price_unit").lower()
    family = _required_text(payload, "material_family").lower()
    if family not in ("steel", "aluminum", "other") or unit not in PRICE_UNITS:
        raise ValueError("Unsupported material family or price unit")
    quantity = _number(payload, "quantity", positive=True)
    days = payload.get("horizon_days", 60)
    if isinstance(days, bool) or not isinstance(days, int) or not 7 <= days <= 365:
        raise ValueError("horizon_days must be an integer from 7 to 365")
    threshold = _number({"threshold":payload.get("spike_threshold_pct", "5")}, "threshold")
    if not 0 < threshold <= 100:
        raise ValueError("spike_threshold_pct must be greater than 0 and at most 100")
    issued = _day(issue_date or date.today().isoformat())
    report = market_pressure(family, as_of=issued, path=path)
    with _connect(path) as db:
        _init(db)
        existing = db.execute("""SELECT * FROM forecast_snapshots WHERE
            issued_date=? AND material_key=? AND supplier=? AND price_unit=? AND
            quantity=? AND horizon_days=?""",
            (issued, material, supplier, unit, str(quantity), days)).fetchone()
        if existing:
            return {"record": _public(existing), "new": False,
                    "message":"Existing snapshot retained without changing historical evidence"}
        baseline = db.execute("""SELECT * FROM purchase_prices WHERE material_key=? AND
            supplier=? AND price_unit=? AND quantity=? AND currency='USD'
            AND source_type='invoice' AND effective_date<=?
            ORDER BY effective_date DESC,id DESC LIMIT 1""",
            (material, supplier, unit, str(quantity), issued)).fetchone()
        if not baseline:
            raise ValueError("A historical verified invoice with exact material, supplier, unit and quantity is required")
        issued_utc = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        cur = db.execute("""INSERT INTO forecast_snapshots (
            issued_date,issued_utc,material_key,material_family,supplier,
            price_unit,quantity,horizon_days,spike_threshold_pct,
            baseline_price_id,baseline_price,baseline_source_ref,risk,
            pressure_score,signal_evidence_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (issued,issued_utc,material,family,supplier,unit,str(quantity),days,
             str(threshold),baseline["id"],baseline["unit_price"],
             baseline["source_ref"],report["risk"],report["pressure_score"],
             json.dumps(report["factors"],sort_keys=True)))
        row = db.execute("SELECT * FROM forecast_snapshots WHERE id=?",(cur.lastrowid,)).fetchone()
    return {"record":_public(row),"new":True,
            "message":"Frozen hypothesis. Outcome only after horizon and subsequent matching invoice."}


def _public(row):
    result = dict(row)
    result["signal_evidence"] = json.loads(result.pop("signal_evidence_json"))
    result["probability_calibrated"] = False
    result["automatic_quote_price_change"] = False
    return result


def evaluate_forecasts(*, path=None, as_of=None, limit=300):
    """Compare matured snapshots to subsequent source-matched invoices.

    Only invoices *recorded after snapshot creation* can establish the outcome.
    Missing observations are unobserved, not a miss or a zero-price invoice.
    """
    day = _day(as_of) if as_of is not None else date.today().isoformat()
    if not isinstance(limit,int) or limit <= 0 or limit>2000:
        raise ValueError("limit must be 1 to 2000")
    samples = []
    with _connect(path) as db:
        _init(db)
        rows = db.execute("""SELECT * FROM forecast_snapshots
                             WHERE issued_date<=? ORDER BY issued_date DESC,id DESC LIMIT ?""",
                          (day,limit)).fetchall()
        for row in rows:
            record = _public(row)
            end = (date.fromisoformat(record["issued_date"]) +
                   timedelta(days=record["horizon_days"])).isoformat()
            record["horizon_end"] = end
            record["status"] = "pending" if end > day else "unobserved"
            record["actual_spike"] = None
            record["predicted_spike"] = None if record["risk"]=="insufficient" else record["risk"] in ("elevated","high")
            record["outcome_invoice"] = None
            record["change_pct"] = None
            if end <= day:
                invoices = db.execute("""SELECT * FROM purchase_prices WHERE material_key=? AND
                    supplier=? AND price_unit=? AND quantity=? AND currency='USD'
                    AND source_type='invoice' AND effective_date>? AND effective_date<=?
                    AND created_utc>?
                    ORDER BY effective_date DESC,id DESC""",
                    (record["material_key"],record["supplier"],record["price_unit"],
                     record["quantity"],record["issued_date"],end,record["issued_utc"])).fetchall()
                if invoices:
                    latest = invoices[0]
                    actual = Decimal(latest["unit_price"])
                    base = Decimal(record["baseline_price"])
                    change = (actual/base-1)*100
                    spike = change >= Decimal(record["spike_threshold_pct"])
                    record.update({"status":"observed" if record["predicted_spike"] is not None else "insufficient_signal",
                                   "actual_spike":spike,"change_pct":str(change.quantize(Decimal("0.01"))),
                                   "outcome_invoice":{"id":latest["id"],
                                                      "source_ref":latest["source_ref"],
                                                      "effective_date":latest["effective_date"],
                                                      "unit_price":latest["unit_price"]}})
            samples.append(record)
    scored = [x for x in samples if x["status"]=="observed"]
    outcomes = [x for x in samples if x["actual_spike"] is not None]
    correct = sum(x["predicted_spike"]==x["actual_spike"] for x in scored)
    always_no_spike = sum(not x["actual_spike"] for x in scored)
    predicted = sum(x["predicted_spike"] for x in scored)
    actual = sum(x["actual_spike"] for x in scored)
    return {"as_of":day,"snapshots":len(samples),"evaluated":len(scored),
            "outcomes_observed":len(outcomes),
            "pending":sum(x["status"]=="pending" for x in samples),
            "unobserved":sum(x["status"]=="unobserved" for x in samples),
            "insufficient_signal":sum(x["status"]=="insufficient_signal" for x in samples),
            "correct":correct,"predicted_spikes":predicted,"actual_spikes":actual,
            "accuracy":str((Decimal(correct)/len(scored)*100).quantize(Decimal("0.1"))) if scored else None,
            "always_no_spike_baseline_accuracy":str(
                (Decimal(always_no_spike)/len(scored)*100).quantize(Decimal("0.1"))) if scored else None,
            "sufficient_to_validate":False, "samples":samples,
            "disclaimer":"Descriptive exact-match post-horizon invoice comparison, not demonstrated predictive advantage or model training."}
