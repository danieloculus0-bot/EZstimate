"""Compare explicit-rate manufacturing quotes across requested lot sizes.

All pricing comes from the supplied route specification; no inferred rates.
Run: python -m ezstimate.quantity_breaks route.json
"""
import argparse
import json
from decimal import Decimal
from .route_estimate import estimate, number


def compare_quantity_breaks(spec):
    if not isinstance(spec, dict):
        raise ValueError("input must be a JSON object")
    quantities = spec.get("quantities")
    if not isinstance(quantities, list) or not quantities:
        raise ValueError("quantities must be a nonempty list")
    if len(quantities) > 100:
        raise ValueError("at most 100 quantities are supported")
    normalized = []
    for i, value in enumerate(quantities):
        qty = number(value, f"quantities[{i}]", positive=True)
        if qty != qty.to_integral_value():
            raise ValueError(f"quantities[{i}] must be an integer")
        if qty in normalized:
            raise ValueError(f"duplicate quantity: {qty}")
        normalized.append(qty)
    route = spec.get("route")
    if not isinstance(route, dict):
        raise ValueError("route must be a JSON object")
    if "quantity" in route:
        raise ValueError("route.quantity is not allowed; use quantities")
    results = []
    for qty in normalized:
        result = estimate({**route, "quantity": int(qty)})
        results.append(result)
    return {
        "status": "draft_quantity_breaks",
        "currency": results[0]["currency"],
        "quotes": results,
        "lowest_sell_each_quantity": results[min(
            range(len(results)),
            key=lambda i: (Decimal(results[i]["sell_each"]), int(results[i]["quantity"]))
        )]["quantity"],
        "note": "Independent draft quotes. No price approval or supplier commitments.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare explicit-rate lot-size quotations")
    parser.add_argument("input", help="JSON containing route and quantities")
    args = parser.parse_args(argv)
    with open(args.input, encoding="utf-8") as handle:
        spec = json.load(handle)
    print(json.dumps(compare_quantity_breaks(spec), indent=2))


if __name__ == "__main__":
    main()
