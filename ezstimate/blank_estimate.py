"""Draft material-use estimates for one known sheet-metal component.

Prefer reviewed flat-pattern area/dimensions. The fallback is deliberately
restricted to a rectangular blank with bends about one parallel axis, using
reviewed sum of outside leg dimensions, not a guessed CAD model or routing.
No quote is approved and no geometry/cost is silently inferred.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from math import pi, tan, radians


def _positive(raw, field, required=True):
    if raw is None or raw == "":
        if required:
            raise ValueError(field + " is required")
        return None
    if isinstance(raw, bool):
        raise ValueError(field + " must be numeric")
    try:
        number = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(field + " must be numeric") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError(field + " must be positive and finite")
    return number


def _nonnegative(raw, field):
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        raise ValueError(field + " must be numeric")
    try:
        number = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(field + " must be numeric") from exc
    if not number.is_finite() or number < 0:
        raise ValueError(field + " must be nonnegative and finite")
    return number


def _show(value, places="0.0001"):
    return str(value.quantize(Decimal(places), rounding=ROUND_HALF_UP))


def estimate_component_blank(payload):
    """Return review-required rectangular blank evidence, not fabrication CAD.

    All dimensions are inches; explicit rate is USD per square inch. Blank
    bounding-box area is NOT shape area, nest yield, or a cutting program.
    """
    if not isinstance(payload, dict):
        raise ValueError("Estimate payload must be an object")
    if payload.get("scope") != "individual_component":
        raise ValueError("Only identified individual components may be estimated; assemblies need a BOM and process details")
    basis = payload.get("basis")
    if basis not in ("flat_pattern", "k_factor_approximation"):
        raise ValueError("Choose a supplied flat pattern or K-factor approximation")

    assumptions = []
    deduction = None
    k_factor = None
    allowance = Decimal(0)
    if basis == "flat_pattern":
        area = _positive(payload.get("flat_area_sq_in"), "flat pattern area", False)
        length = _positive(payload.get("flat_length_in"), "flat pattern length", False)
        width = _positive(payload.get("flat_width_in"), "flat pattern width", False)
        if area is None and (length is None or width is None):
            raise ValueError("Supply reviewed flat-pattern area or both flat dimensions")
        if (length is None) != (width is None):
            raise ValueError("Supply both flat dimensions together")
        box = length * width if length is not None else None
        if area is not None and box is not None and area > box:
            raise ValueError("Flat-pattern area exceeds its bounding rectangle; review dimensions and units")
        material_area = area if area is not None else box
        if area is None:
            assumptions.append("Rectangular bounding-box area; complex cutouts and irregular outlines need reviewed actual area")
        else:
            assumptions.append("Reviewed flat-pattern area supplied; no K-factor or cushion applied")
    else:
        total = _positive(payload.get("outside_leg_sum_in"), "sum of outside leg dimensions")
        width = _positive(payload.get("blank_width_in"), "blank width")
        thickness = _positive(payload.get("thickness_in"), "material thickness")
        radius = _nonnegative(payload.get("inside_radius_in"), "inside bend radius")
        if radius is None:
            raise ValueError("Inside bend radius is required; do not guess tooling")
        angle = _positive(payload.get("bend_angle_deg"), "bend angle")
        count = _positive(payload.get("bend_count"), "bend count")
        k_factor = _positive(payload.get("k_factor", "0.44"), "K-factor")
        allowance = _nonnegative(payload.get("cushion_in", "0.030"), "dimension cushion")
        if count != count.to_integral_value() or count > 40:
            raise ValueError("Bend count must be a whole number from 1 to 40")
        if angle >= 180:
            raise ValueError("Bend angle must be under 180 degrees")
        if not Decimal("0.20") <= k_factor <= Decimal("0.50"):
            raise ValueError("K-factor must be between 0.20 and 0.50")
        if allowance > Decimal("0.250"):
            raise ValueError("Dimension cushion cannot exceed 0.250 in")
        tangent = Decimal(str(tan(radians(float(angle)) / 2)))
        radians_angle = Decimal(str(pi)) * angle / Decimal(180)
        deduction = 2 * (radius + thickness) * tangent - radians_angle * (radius + k_factor * thickness)
        length = total - count * deduction + allowance
        width = width + allowance
        if length <= 0:
            raise ValueError("Bend deductions exhaust the supplied outside dimensions; review geometry")
        box = length * width
        material_area = box
        assumptions.extend((
            "Estimate only: outside leg dimensions must describe a simple part bent about one parallel axis",
            "One reviewed bend angle and inside radius applied to all bends; other bend layouts require a flat pattern",
            "Configured cushion applies once to estimated length and width, not per bend",
            "Rectangular bounding-box area only; nesting yield and scrap remain separate quote inputs",
        ))

    price = _nonnegative(payload.get("material_price_per_sq_in"), "material price per square inch")
    material_cost = material_area * price if price is not None else None
    return {
        "schema": "ezstimate.component_blank_estimate.v1",
        "status": "draft_review",
        "scope": "individual_component",
        "basis": basis,
        "length_in": _show(length) if length is not None else None,
        "width_in": _show(width) if width is not None else None,
        "bounding_box_area_sq_in": _show(box) if box is not None else None,
        "material_area_sq_in": _show(material_area),
        "material_cost_each": _show(material_cost, "0.01") if material_cost is not None else None,
        "material_price_per_sq_in": str(price) if price is not None else None,
        "k_factor": str(k_factor) if k_factor is not None else None,
        "cushion_in": str(allowance),
        "bend_deduction_each_in": _show(deduction) if deduction is not None else None,
        "assumptions": assumptions,
        "needs_review": True,
        "approved": False,
    }
