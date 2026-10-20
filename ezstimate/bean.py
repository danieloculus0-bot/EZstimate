"""Optional bridge into REAL BEAN Core persistence.

Fallback recommendations are plain EZstimate rules and must never be described
as autonomous BEAN inference. The host remains authoritative for quote release.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os

def local_review(documents, quote):
    findings = []
    keys = {key for d in documents for key in d.get("fields", {})}
    if "material" not in keys:
        findings.append("Confirm material, grade, thickness, stock form and actual purchasing cost.")
    if "revision" not in keys:
        findings.append("Confirm the controlled drawing revision before pricing.")
    if quote.get("status") != "draft_review":
        findings.append("Unpriced or invalid quote lines block the estimate total.")
    if not any(d.get("kind") == "purchase_order" for d in documents):
        findings.append("No PO found; confirm requested quantity, revision, ship date and commercial terms.")
    if any(not d.get("bom") for d in documents if d.get("kind") == "drawing"):
        findings.append("One or more drawings have no detected BOM table. Cross-check assembly components.")
    if not findings:
        findings.append("Basic document/quote completeness checks passed. Validate routing and supplier costs before release.")
    return {"engine": "EZstimate deterministic local checks", "bean_core_invoked": False,
            "findings": findings, "authority": "advisory_only"}

def core_status():
    configured = bool(os.environ.get("EZSTIMATE_BEAN_DB"))
    try:
        installed = bool(importlib.util.find_spec("bean"))
    except (ImportError, ModuleNotFoundError):
        installed = False
    return {"configured": configured, "core_importable": installed,
            "mode": "opt_in" if configured else "disabled"}

def journal(documents, quote, assessment):
    path = os.environ.get("EZSTIMATE_BEAN_DB")
    if not path:
        return {"connected": False, "reason": "EZSTIMATE_BEAN_DB not configured"}
    try:
        from bean.integration import BeanReasoningLayer
    except ImportError:
        return {"connected": False, "reason": "Real BEAN Core not installed"}
    evidence = [
        {"source": d.get("filename"), "kind": d.get("kind"), "bom_count": len(d.get("bom", [])),
         "fields": {k: {"value": v["value"], "page": v.get("page"),
                        "region": v.get("region")} for k, v in d.get("fields", {}).items()}}
        for d in documents
    ]
    observation = {"schema": "ezstimate.source_observation.v1",
                   "evidence": evidence, "quote_status": quote.get("status"),
                   "quote_total": quote.get("total"), "findings": assessment.get("findings", []),
                   "human_approved": False}
    fingerprint = hashlib.sha256(json.dumps(observation, sort_keys=True).encode("utf-8")).hexdigest()
    with BeanReasoningLayer(path) as core:
        event_id = core.record_event("EZstimate draft quote source review",
                                     subtype="ezstimate", data={"sha256": fingerprint, **observation})
    return {"connected": True, "bean_core_invoked": True,
            "event_id": event_id, "fingerprint": fingerprint,
            "authority": "observation_only"}


def journal_market_review(report):
    """Persist a source-backed market-pressure observation in real BEAN Core, if installed.

    No model inference is implied. Forecasting remains a hypothesis to validate
    against later purchasing prices.
    """
    path = os.environ.get("EZSTIMATE_BEAN_DB")
    if not path:
        return {"connected": False, "reason": "EZSTIMATE_BEAN_DB not configured"}
    try:
        from bean.integration import BeanReasoningLayer
    except ImportError:
        return {"connected": False, "reason": "Real BEAN Core not installed"}
    evidence = {
        "schema": "ezstimate.market_pressure.v1",
        "material_family": report["family"],
        "as_of": report["as_of"],
        "pressure_score": report["pressure_score"],
        "risk": report["risk"],
        "factors": report["factors"],
        "supplier_price_forecast": None,
        "forecast_accuracy_unverified": True,
        "auto_pricing": False,
    }
    fingerprint = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode("utf-8")).hexdigest()
    with BeanReasoningLayer(path) as core:
        event_id = core.record_event("EZstimate observed material market pressure",
                                     subtype="ezstimate_material_market",
                                     data={"sha256": fingerprint, **evidence})
    return {"connected": True, "bean_core_invoked": True, "event_id": event_id,
            "fingerprint": fingerprint, "authority": "observation_only",
            "model_inference": False}


def journal_forecast_assessment(report):
    """Record actual prospective-vs-invoice receipts into installed BEAN Core.

    This is evidence persistence for later policy comparisons, not training.
    """
    path = os.environ.get("EZSTIMATE_BEAN_DB")
    if not path:
        return {"connected": False, "reason": "EZSTIMATE_BEAN_DB not configured"}
    try:
        from bean.integration import BeanReasoningLayer
    except ImportError:
        return {"connected": False, "reason": "Real BEAN Core not installed"}
    evidence = {
        "schema": "ezstimate.forecast_evaluation.v1",
        "as_of": report["as_of"],
        "snapshots": report["snapshots"],
        "evaluated": report["evaluated"],
        "outcomes_observed": report["outcomes_observed"],
        "correct": report["correct"],
        "accuracy": report["accuracy"],
        "always_no_spike_baseline_accuracy": report["always_no_spike_baseline_accuracy"],
        "samples": [{
            "forecast_id": s["id"],
            "issued_date": s["issued_date"],
            "material_key": s["material_key"],
            "risk": s["risk"],
            "baseline_price": s["baseline_price"],
            "baseline_source_ref": s["baseline_source_ref"],
            "outcome_invoice": s["outcome_invoice"],
            "change_pct": s["change_pct"],
            "status": s["status"]
        } for s in report["samples"][:25]],
        "trained_model": False,
        "demonstrated_advantage": False
    }
    fingerprint = hashlib.sha256(json.dumps(evidence,sort_keys=True).encode("utf-8")).hexdigest()
    with BeanReasoningLayer(path) as core:
        event_id = core.record_event("EZstimate actual invoice vs prior market warning",
                                     subtype="ezstimate_price_validation",
                                     data={"sha256":fingerprint, **evidence})
    return {"connected":True,"bean_core_invoked":True,"event_id":event_id,
            "fingerprint":fingerprint,"authority":"evidence_only",
            "model_trained":False}
