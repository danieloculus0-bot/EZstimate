"""Local-only Flask UI. Uploaded source bytes are inspected in memory."""
from __future__ import annotations
import os
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory
from .engine import inspect_document, price_quote, review_package
from .bean import local_review, core_status, journal, journal_market_review, journal_forecast_assessment
from .pricing import remember_price, price_history, record_market_signal, market_pressure, database_path
from .mid_adapter import preview_mid
from .market_feeds import refresh_official_feeds, SOURCES, DIESEL_SERIES
from .forecast import freeze_forecast, evaluate_forecasts
from .procurement import (create_request, get_request, recent_requests,
                          approve_and_dispatch, dispatch_request)
from .erp_adapters import DispatchError

ROOT = Path(__file__).resolve().parent.parent
app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 20_000_000

@app.after_request
def protect(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self'; script-src 'self'; "
        "img-src 'self' data:; object-src 'none'; base-uri 'none'")
    return response

@app.get("/")
def index():
    return send_from_directory(ROOT / "web", "index.html")

@app.get("/<path:filename>")
def assets(filename):
    if filename not in ("app.js", "style.css", "bean-official.webp"):
        return jsonify({"error": "not found"}), 404
    return send_from_directory(ROOT / "web", filename)

@app.get("/api/status")
def status():
    return jsonify({"product": "EZstimate", "scope": "experimental alpha", "bean": core_status()})

@app.post("/api/intake")
def intake():
    uploads = request.files.getlist("files")
    if not 1 <= len(uploads) <= 12:
        return jsonify({"error": "Supply 1-12 PDF, CSV or XLSX documents"}), 400
    documents, errors = [], []
    for upload in uploads:
        try:
            if not upload.filename:
                raise ValueError("Missing filename")
            documents.append(inspect_document(upload.filename, upload.read()))
        except (ValueError, RuntimeError, UnicodeError) as exc:
            errors.append({"filename": upload.filename, "message": str(exc)})
    return jsonify({"documents": documents, "issues": review_package(documents), "errors": errors})

@app.post("/api/quote")
def quote():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "JSON object required"}), 400
    return jsonify(price_quote(body))

@app.post("/api/bean/review")
def bean_review():
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get("documents", []), list):
        return jsonify({"error": "Valid document set required"}), 400
    documents = body.get("documents", [])
    if len(documents) > 12:
        return jsonify({"error": "Too many source documents"}), 400
    quote_result = price_quote(body.get("quote", {}))
    advice = local_review(documents, quote_result)
    result = {"review": advice, "issues": review_package(documents), "bean": core_status(),
              "journal": None}
    if body.get("journal") is True:
        try:
            result["journal"] = journal(documents, quote_result, advice)
        except Exception as exc:
            return jsonify({"error": "BEAN persistence not confirmed",
                            "detail": type(exc).__name__}), 503
    return jsonify(result)


@app.post("/api/pricing/mid-preview")
def mid_workbook_preview():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify({"error": "Provide an MID XLSX workbook"}), 400
    try:
        return jsonify(preview_mid(upload.filename, upload.read()))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

@app.get("/api/pricing/status")
def pricing_status():
    return jsonify({"backend": "local_sqlite", "database": str(database_path()),
                    "price_memory": "persistent", "market_feed": "BLS_public_api_and_optional_EIA",
                    "eia_key_configured": bool(os.environ.get("EIA_API_KEY")),
                    "quote_autofill": False, "market_quote_escalation": False})

@app.post("/api/pricing/prices")
def remember_purchase_price():
    try:
        data = request.get_json(silent=True)
        result = remember_price(data)
        return jsonify(result), 201 if result["new"] else 200
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400

@app.get("/api/pricing/prices")
def historical_prices():
    try:
        return jsonify(price_history(request.args.get("material_key", ""),
                                    request.args.get("price_unit", ""),
                                    supplier=request.args.get("supplier") or None,
                                    as_of=request.args.get("as_of") or None))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

@app.post("/api/pricing/signals")
def new_market_signal():
    try:
        data = request.get_json(silent=True)
        result = record_market_signal(data)
        return jsonify(result), 201 if result["new"] else 200
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400

@app.get("/api/pricing/pressure")
def market_pressure_report():
    try:
        return jsonify(market_pressure(request.args.get("family", "steel"),
                                      as_of=request.args.get("as_of") or None))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

@app.post("/api/bean/market-observation")
def bean_market_observation():
    try:
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ValueError("Object required")
        # Recompute from persisted, dated inputs, not user-supplied risk labels.
        report = market_pressure(body.get("family", "steel"))
        result = journal_market_review(report)
        return jsonify({"assessment": report, "journal": result})
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
    except (ImportError, RuntimeError, OSError) as exc:
        return jsonify({"error": "BEAN Core journal unavailable", "reason": type(exc).__name__}), 503


@app.get("/api/pricing/feeds/status")
def official_feed_status():
    return jsonify({"bls_series": {k: v[0] for k,v in SOURCES.items()},
                    "eia_diesel_series": DIESEL_SERIES,
                    "eia_key_configured": bool(os.environ.get("EIA_API_KEY")),
                    "public_data_only": True, "auto_quote_change": False,
                    "refresh": "explicit_local_only"})

@app.post("/api/pricing/feeds/refresh")
def refresh_feed():
    # This local-only action reaches fixed official provider URLs; it does not
    # accept caller-supplied arbitrary HTTP destinations or API credentials.
    return jsonify(refresh_official_feeds())

@app.post("/api/pricing/forecasts")
def issue_market_forecast():
    try:
        body = request.get_json(silent=True)
        result = freeze_forecast(body)
        return jsonify(result), 201 if result["new"] else 200
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400

@app.get("/api/pricing/forecasts")
def forecast_scorecard():
    try:
        return jsonify(evaluate_forecasts())
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400

@app.post("/api/bean/forecast-outcomes")
def journal_forecast_outcomes():
    try:
        report = evaluate_forecasts()
        return jsonify({"scorecard": report, "journal": journal_forecast_assessment(report)})
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
    except (ImportError, RuntimeError, OSError) as exc:
        return jsonify({"error": "BEAN Core journal unavailable", "reason": type(exc).__name__}), 503


@app.get("/api/procurement/status")
def procurement_status():
    mode=os.environ.get("EZSTIMATE_ERP_MODE","").lower()
    return jsonify({"approval_configured":bool(os.environ.get("EZSTIMATE_APPROVAL_TOKEN")),
                    "dispatch_mode":mode or "not_configured",
                    "outbound_configured":mode in ("outbox","https"),
                    "auto_dispatch_after_approval":mode in ("outbox","https"),
                    "erp_accepted_not_asserted":True})

@app.post("/api/procurement/requests")
def new_purchase_request():
    try:
        result=create_request(request.get_json(silent=True))
        return jsonify(result),201 if result["new"] else 200
    except (ValueError,TypeError) as exc:
        return jsonify({"error":str(exc)}),400

@app.get("/api/procurement/requests")
def list_purchase_requests():
    return jsonify(recent_requests())

@app.get("/api/procurement/requests/<request_id>")
def purchase_request_details(request_id):
    try:
        return jsonify(get_request(request_id))
    except ValueError as exc:
        return jsonify({"error":str(exc)}),404

@app.post("/api/procurement/requests/<request_id>/approve")
def approve_purchase_request(request_id):
    body=request.get_json(silent=True)
    if not isinstance(body,dict):
        return jsonify({"error":"JSON object required"}),400
    try:
        result=approve_and_dispatch(request_id,body.get("approver"),
                                    request.headers.get("X-EZstimate-Approval-Token"),
                                    path=None)
        return jsonify(result)
    except PermissionError as exc:
        return jsonify({"error":str(exc)}),403
    except (ValueError,TypeError) as exc:
        return jsonify({"error":str(exc)}),400

@app.post("/api/procurement/requests/<request_id>/dispatch")
def dispatch_purchase_request(request_id):
    try:
        result=dispatch_request(request_id,
            request.headers.get("X-EZstimate-Approval-Token"))
        return jsonify(result)
    except PermissionError as exc:
        return jsonify({"error":str(exc)}),403
    except (ValueError,TypeError) as exc:
        return jsonify({"error":str(exc)}),400
    except DispatchError as exc:
        return jsonify({"error":str(exc),"delivery_unknown":exc.uncertain}),502

def main():
    from .auto_refresh import start_market_refresh
    start_market_refresh()
    app.run(host="127.0.0.1", port=int(os.environ.get("EZSTIMATE_PORT", "8765")), debug=False)

if __name__ == "__main__":
    main()
