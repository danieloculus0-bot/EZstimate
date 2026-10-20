"""Local, auditable purchasing-price memory and market-pressure signals.

This module never changes quote arithmetic or treats a forecast as a supplier price.
All prices and signals are supplied by the operator; there is no live data feed.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
import sqlite3

PRICE_SOURCES = {"supplier_quote", "purchase_order", "invoice", "verified_manual"}
PRICE_UNITS = {"ea", "sheet", "lb", "kg", "ft", "m"}
SERIES_UNITS = {
    "diesel_usd_per_gallon": "USD/gal",
    "steel_market_index": "index",
    "aluminum_market_index": "index",
    "supplier_lead_days": "days",
    "sentiment_score": "points",
}


def database_path():
    configured = os.environ.get("EZSTIMATE_PRICE_DB")
    return Path(configured).expanduser() if configured else Path.home() / ".ezstimate" / "price_memory.sqlite3"


@contextmanager
def _connect(path=None):
    target = Path(path) if path is not None else database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(target), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=10000")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS purchase_prices (
          id INTEGER PRIMARY KEY,
          material_key TEXT NOT NULL,
          supplier TEXT NOT NULL,
          source_type TEXT NOT NULL,
          source_ref TEXT NOT NULL,
          effective_date TEXT NOT NULL,
          unit_price TEXT NOT NULL,
          price_unit TEXT NOT NULL,
          quantity TEXT NOT NULL,
          currency TEXT NOT NULL,
          notes TEXT NOT NULL DEFAULT '',
          created_utc TEXT NOT NULL,
          UNIQUE(material_key, supplier, source_type, source_ref, effective_date, price_unit, quantity)
        );
        CREATE INDEX IF NOT EXISTS price_lookup ON purchase_prices
          (material_key, price_unit, currency, effective_date DESC);
        CREATE TABLE IF NOT EXISTS market_signals (
          id INTEGER PRIMARY KEY,
          series TEXT NOT NULL,
          value TEXT NOT NULL,
          unit TEXT NOT NULL,
          effective_date TEXT NOT NULL,
          source TEXT NOT NULL,
          notes TEXT NOT NULL DEFAULT '',
          created_utc TEXT NOT NULL,
          UNIQUE(series, effective_date, source)
        );
        CREATE INDEX IF NOT EXISTS signal_lookup ON market_signals(series, effective_date DESC);
    """)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _required_text(data, field, maxlen=200):
    value = str(data.get(field, "")).strip()
    if not value or len(value) > maxlen:
        raise ValueError(f"{field} must be a nonempty string of at most {maxlen} characters")
    return value


def _number(data, field, positive=False):
    try:
        raw = data.get(field)
        if raw is None or isinstance(raw, bool):
            raise ValueError()
        value = Decimal(str(raw))
        if not value.is_finite() or (value <= 0 if positive else value < 0):
            raise ValueError()
        return value
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be a finite {'positive' if positive else 'nonnegative'} number") from None


def _day(raw, field="effective_date"):
    if not isinstance(raw, str):
        raise ValueError(f"{field} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        raise ValueError(f"{field} must be YYYY-MM-DD") from None
    if parsed.isoformat() != raw or parsed > datetime.now(timezone.utc).date():
        raise ValueError(f"{field} must be a valid date not in the future")
    return raw


def _as_of(raw):
    return _day(raw, "as_of") if raw else datetime.now(timezone.utc).date().isoformat()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def remember_price(item, path=None):
    """Persist a dated purchase-price observation, never a speculative cost."""
    if not isinstance(item, dict):
        raise ValueError("Price record must be an object")
    material_key = _required_text(item, "material_key").upper()
    supplier = _required_text(item, "supplier")
    source_type = _required_text(item, "source_type")
    source_ref = _required_text(item, "source_ref")
    effective_date = _day(item.get("effective_date"))
    price_unit = _required_text(item, "price_unit").lower()
    currency = _required_text(item, "currency").upper()
    quantity = _number(item, "quantity", positive=True)
    price = _number(item, "unit_price", positive=True)
    if source_type not in PRICE_SOURCES:
        raise ValueError("source_type must be supplier_quote, purchase_order, invoice, or verified_manual")
    if price_unit not in PRICE_UNITS:
        raise ValueError("Unsupported price_unit")
    if currency != "USD":
        raise ValueError("Only USD pricing is supported; do not silently convert currency")
    notes = str(item.get("notes") or "")[:1000]
    args = (material_key, supplier, source_type, source_ref, effective_date, str(price),
            price_unit, str(quantity), currency, notes, _now())
    with _connect(path) as db:
        existing = db.execute("""SELECT * FROM purchase_prices WHERE material_key=?
          AND supplier=? AND source_type=? AND source_ref=? AND effective_date=?
          AND price_unit=? AND quantity=?""",
          (material_key, supplier, source_type, source_ref, effective_date,
           price_unit, str(quantity))).fetchone()
        if existing:
            if existing["unit_price"] != str(price) or existing["currency"] != currency:
                raise ValueError("Conflicting price for the same source; use a new revision/reference")
            return {"record": dict(existing), "new": False}
        cur = db.execute("""INSERT INTO purchase_prices
           (material_key,supplier,source_type,source_ref,effective_date,unit_price,
            price_unit,quantity,currency,notes,created_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?)""", args)
        record = db.execute("SELECT * FROM purchase_prices WHERE id=?", (cur.lastrowid,)).fetchone()
        return {"record": dict(record), "new": True}


def price_history(material_key, price_unit, currency="USD", supplier=None, as_of=None, path=None):
    """Exact material code/unit/currency lookup; return candidates, never alter quote inputs."""
    key = str(material_key).strip().upper()
    unit = str(price_unit).strip().lower()
    if not key or unit not in PRICE_UNITS or currency != "USD":
        raise ValueError("A material_key, supported price_unit, and USD currency are required")
    day = _as_of(as_of)
    params = [key, unit, currency, day]
    sql = """SELECT * FROM purchase_prices
             WHERE material_key=? AND price_unit=? AND currency=? AND effective_date<=?"""
    if supplier:
        sql += " AND supplier=?"
        params.append(supplier)
    sql += " ORDER BY effective_date DESC, id DESC LIMIT 100"
    with _connect(path) as db:
        rows = [dict(row) for row in db.execute(sql, params)]
    for row in rows:
        row["age_days"] = (date.fromisoformat(day)-date.fromisoformat(row["effective_date"])).days
        row["stale_90d"] = row["age_days"] > 90
    return {"material_key": key, "price_unit": unit, "currency": currency,
            "as_of": day, "candidate": rows[0] if rows else None,
            "history": rows, "auto_applied": False,
            "message": "Historical evidence only. Select and verify a price before using it."}


def record_market_signal(item, path=None):
    if not isinstance(item, dict):
        raise ValueError("Signal record must be an object")
    series = _required_text(item, "series")
    if series not in SERIES_UNITS:
        raise ValueError("Unsupported market series")
    value = _number(item, "value", positive=False)
    if series == "sentiment_score" and value > 100:
        raise ValueError("sentiment_score must be 0 to 100")
    effective_date = _day(item.get("effective_date"))
    source = _required_text(item, "source")
    notes = str(item.get("notes") or "")[:1000]
    with _connect(path) as db:
        existing = db.execute("""SELECT * FROM market_signals WHERE
                                series=? AND effective_date=? AND source=?""",
                              (series, effective_date, source)).fetchone()
        if existing:
            if existing["value"] != str(value):
                raise ValueError("Conflicting market reading: enter a separate source/revision")
            return {"record": dict(existing), "new": False}
        cur = db.execute("""INSERT INTO market_signals
            (series,value,unit,effective_date,source,notes,created_utc)
            VALUES (?,?,?,?,?,?,?)""",
            (series, str(value), SERIES_UNITS[series], effective_date, source, notes, _now()))
        return {"record": dict(db.execute("SELECT * FROM market_signals WHERE id=?",
                                         (cur.lastrowid,)).fetchone()), "new": True}


def market_pressure(family="steel", as_of=None, path=None):
    """Transparent trend heuristics, not a price prediction or a quote escalation."""
    family = str(family).strip().lower()
    if family not in {"steel", "aluminum", "other"}:
        raise ValueError("family must be steel, aluminum, or other")
    day = _as_of(as_of)
    series = ["diesel_usd_per_gallon", "supplier_lead_days", "sentiment_score"]
    if family in {"steel", "aluminum"}:
        series.append(f"{family}_market_index")
    with _connect(path) as db:
        sampled = {s: [dict(r) for r in db.execute(
            """SELECT * FROM market_signals WHERE series=? AND effective_date<=?
               ORDER BY effective_date DESC, id DESC LIMIT 2""", (s, day))] for s in series}
    score, factors, reasons = 0, [], []
    for s, history in sampled.items():
        if not history:
            factors.append({"series": s, "status": "missing"})
            continue
        current = history[0]
        previous = history[1] if len(history)>1 else None
        change_pct = None
        if previous and Decimal(previous["value"]) != 0:
            change_pct = (Decimal(current["value"])/Decimal(previous["value"])-1)*100
        points = 0
        if change_pct is not None:
            if s.endswith("market_index"):
                points = 3 if change_pct >= 10 else 2 if change_pct >= 5 else 0
            elif s == "diesel_usd_per_gallon":
                points = 2 if change_pct >= 10 else 1 if change_pct >= 5 else 0
            elif s == "supplier_lead_days":
                points = 2 if change_pct >= 40 else 1 if change_pct >= 20 else 0
        elif s == "sentiment_score" and Decimal(current["value"]) >= 70:
            points = 1
        # Stale signals are visible but do not score as current pressure.
        age = (date.fromisoformat(day)-date.fromisoformat(current["effective_date"])).days
        if age > 90:
            points = 0
        score += points
        if points:
            reasons.append(f"{s}: {str(change_pct.quantize(Decimal('0.1'))) + '%' if change_pct is not None else 'elevated'}")
        factors.append({"series": s, "status": "stale" if age>90 else "observed",
                        "latest": current, "previous": previous,
                        "change_pct": str(change_pct.quantize(Decimal("0.1"))) if change_pct is not None else None,
                        "age_days": age, "pressure_points": points})
    comparable = sum(1 for x in factors if x.get("status")=="observed" and x.get("previous"))
    label = "insufficient" if comparable==0 else "high" if score>=4 else "elevated" if score>=2 else "monitor"
    return {"family": family, "as_of": day, "pressure_score": score, "risk": label,
            "spike_watch": label=="high", "factors": factors, "reasons": reasons,
            "comparison_series": comparable, "kind": "market_pressure_watch",
            "forecasted_price": None, "auto_applied_to_quote": False,
            "disclaimer": "Market indicators are historical pressure signals, not a supplier quote or proven probability of a price spike."}
