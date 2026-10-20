"""Local-only Flask UI. Uploaded source bytes are inspected in memory."""
from __future__ import annotations
import os
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory
from .engine import inspect_document, price_quote, review_package
from .bean import local_review, core_status, journal

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
    if filename not in ("app.js", "style.css"):
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

def main():
    app.run(host="127.0.0.1", port=int(os.environ.get("EZSTIMATE_PORT", "8765")), debug=False)

if __name__ == "__main__":
    main()
