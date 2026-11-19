"""Explicit-rate fabrication routing estimator. No inferred prices or machine instructions."""
import argparse
import json
import math
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

OPERATIONS = {"laser": "length_mm", "plasma": "length_mm", "brake": "bends", "weld": "length_mm", "machining": "minutes", "powder": "area_m2", "inspection": "minutes"}

def number(value, label, *, positive=False):
    if isinstance(value, bool):
        raise ValueError(f"{label}: numeric value required")
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{label}: numeric value required") from None
    if not d.is_finite() or d < 0 or (positive and d == 0):
        raise ValueError(f"{label}: value must be {'positive' if positive else 'nonnegative'} and finite")
    return d

def estimate(spec):
    """Return auditable totals; rates are supplied per operation unit, never invented."""
    if not isinstance(spec, dict):
        raise ValueError("input must be a JSON object")
    quantity = number(spec.get("quantity"), "quantity", positive=True)
    if quantity != quantity.to_integral_value():
        raise ValueError("quantity must be an integer")
    margin = number(spec.get("gross_margin_percent", 0), "gross_margin_percent")
    if margin >= 100:
        raise ValueError("gross_margin_percent must be below 100")
    material_each = number(spec.get("material_each"), "material_each")
    scrap_percent = number(spec.get("scrap_percent", 0), "scrap_percent")
    if scrap_percent >= 100:
        raise ValueError("scrap_percent must be below 100")
    operations = spec.get("operations")
    if not isinstance(operations, list):
        raise ValueError("operations must be a list")
    lines = []
    routing_each = Decimal(0)
    for i, op in enumerate(operations):
        if not isinstance(op, dict) or op.get("process") not in OPERATIONS:
            raise ValueError(f"operations[{i}]: unsupported process")
        process = op["process"]
        unit = OPERATIONS[process]
        amount = number(op.get(unit), f"operations[{i}].{unit}")
        rate = number(op.get("rate_per_unit"), f"operations[{i}].rate_per_unit")
        setup = number(op.get("setup_cost", 0), f"operations[{i}].setup_cost")
        cost_each = amount * rate + setup / quantity
        routing_each += cost_each
        lines.append({"process": process, "unit": unit, "quantity_each": str(amount), "rate_per_unit": str(rate), "setup_total": str(setup), "cost_each": str(cost_each)})
    material_with_scrap = material_each / (Decimal(1) - scrap_percent / 100)
    cost_each = material_with_scrap + routing_each
    sell_each = cost_each / (Decimal(1) - margin / 100)
    money = lambda x: str(x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return {"quantity": int(quantity), "operations": lines, "material_with_scrap_each": money(material_with_scrap), "routing_cost_each": money(routing_each), "cost_each": money(cost_each), "cost_total": money(cost_each * quantity), "sell_each": money(sell_each), "sell_total": money(sell_each * quantity), "currency": spec.get("currency", "USD"), "status": "draft_explicit_rates"}

def main(argv=None):
    parser = argparse.ArgumentParser(description="Estimate a draft fabrication route using explicit unit rates")
    parser.add_argument("input", help="JSON route input")
    args = parser.parse_args(argv)
    with open(args.input, encoding="utf-8") as f:
        spec = json.load(f)
    print(json.dumps(estimate(spec), indent=2))

if __name__ == "__main__":
    main()
