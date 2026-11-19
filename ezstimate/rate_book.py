"""Resolve explicitly approved, effective-dated unit rates into draft route estimates.

Never substitutes missing rates or changes the source rate book.
"""
import argparse
import json
from datetime import date
from decimal import Decimal
from .route_estimate import OPERATIONS, estimate, number


def resolve(spec, book, as_of):
    if not isinstance(spec, dict) or not isinstance(book, dict):
        raise ValueError("route and rate book must be JSON objects")
    day = date.fromisoformat(as_of)
    currency = book.get("currency")
    if not isinstance(currency, str) or not currency.strip():
        raise ValueError("rate book currency required")
    if spec.get("currency", currency) != currency:
        raise ValueError("route and rate book currencies differ")
    entries = book.get("rates")
    if not isinstance(entries, list):
        raise ValueError("rates must be a list")
    indexed = {}
    for i, item in enumerate(entries):
        if not isinstance(item, dict):
            raise ValueError(f"rates[{i}] must be an object")
        process = item.get("process")
        if process not in OPERATIONS or item.get("unit") != OPERATIONS[process]:
            raise ValueError(f"rates[{i}] process/unit mismatch")
        start = date.fromisoformat(item["effective_from"])
        end = date.fromisoformat(item["effective_to"]) if item.get("effective_to") else None
        if end is not None and end < start:
            raise ValueError(f"rates[{i}] invalid date range")
        rate = number(item.get("rate_per_unit"), f"rates[{i}].rate_per_unit")
        key = (process, start, end)
        if key in indexed:
            raise ValueError(f"rates[{i}] duplicate period")
        indexed[key] = (rate, i)
    out = dict(spec)
    out["currency"] = currency
    resolved = []
    provenance = []
    for i, operation in enumerate(spec.get("operations", [])):
        if not isinstance(operation, dict):
            raise ValueError(f"operations[{i}] must be an object")
        process = operation.get("process")
        if process not in OPERATIONS:
            raise ValueError(f"operations[{i}] unsupported process")
        if "rate_per_unit" in operation:
            raise ValueError(f"operations[{i}] inline rate conflicts with rate book")
        matches = [(rate, index) for (p, start, end), (rate, index) in indexed.items()
                   if p == process and start <= day and (end is None or day <= end)]
        if len(matches) != 1:
            raise ValueError(f"operations[{i}] expected one effective rate for {process}, found {len(matches)}")
        rate, index = matches[0]
        row = dict(operation)
        row["rate_per_unit"] = str(rate)
        resolved.append(row)
        provenance.append({"operation_index": i, "rate_book_index": index, "process": process,
                           "effective_date": day.isoformat()})
    out["operations"] = resolved
    result = estimate(out)
    result["rate_provenance"] = provenance
    result["rate_book_version"] = book.get("version")
    result["rate_effective_date"] = day.isoformat()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Estimate a draft route with dated explicit unit rates")
    parser.add_argument("route")
    parser.add_argument("rate_book")
    parser.add_argument("--as-of", required=True, help="YYYY-MM-DD")
    args = parser.parse_args(argv)
    with open(args.route, encoding="utf-8") as stream:
        route = json.load(stream)
    with open(args.rate_book, encoding="utf-8") as stream:
        book = json.load(stream)
    print(json.dumps(resolve(route, book, args.as_of), indent=2))


if __name__ == "__main__":
    main()
