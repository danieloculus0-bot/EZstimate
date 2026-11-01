"""Reviewable fabrication callouts from selectable engineering-drawing text.

This is not a geometric or visual feature detector. All candidates retain their
source line and page; missing count/radius/size/length stay unknown.
"""
from __future__ import annotations
import re

BENDS = re.compile(r"\b(?:BENDS?|BRAKE\s+FORM(?:ING)?|FORM(?:ING|ED)?|FLANGES?)\b", re.I)
WELDS = re.compile(r"\b(?:WELD(?:MENT|ED|ING|S)?|FILLET|SEAM|BEAD|TACK|STITCH|GMAW|GTAW|MIG|TIG)\b", re.I)
RADIUS = re.compile(r"\b(?:INSIDE\s+)?(?:BEND\s+)?(?:RADIUS|RAD\.?|R)\s*[:=]?\s*(\d+(?:\.\d+)?|\.\d+)\b", re.I)
ANGLE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:°|DEG(?:REES?)?\b)", re.I)
MULTIPLE = re.compile(r"\b(\d+)\s*(?:X|PLCS?|PLACES)\b", re.I)
BEND_COUNT = re.compile(r"\b(\d+)\s+BENDS?\b", re.I)
WELD_SIZE = re.compile(r"\b(\d+\s*/\s*\d+|\d+(?:\.\d+)?|\.\d+)\s*(?:IN(?:CH(?:ES)?)?|\x22)?\s+FILLET\b", re.I)
WELD_LENGTH = re.compile(r"\b(?:WELD\s+)?(?:LENGTH|LEN|LG)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(MM|IN(?:CH(?:ES)?)?)?\b", re.I)


def extract_fabrication_features(regions, filename):
    """One source-backed candidate per operation-bearing line, never inferred geometry."""
    seen, features = set(), []
    for region in regions:
        if region.get("region") != "full page":
            continue  # title-block crop duplicates full-page source
        page = region.get("page")
        for line in region.get("text", "").splitlines():
            raw = line.strip()
            if not raw or len(raw) > 250:
                continue
            kinds = (("bending", BENDS), ("welding", WELDS))
            for process, pattern in kinds:
                if not pattern.search(raw):
                    continue
                key = (page, process, re.sub(r"\s+", " ", raw).casefold())
                if key in seen:
                    continue
                seen.add(key)
                attributes = {}
                if process == "bending":
                    radius, angle = RADIUS.search(raw), ANGLE.search(raw)
                    count = BEND_COUNT.search(raw) or MULTIPLE.search(raw)
                    attributes = {"radius": radius.group(1) if radius else None,
                                  "angle_degrees": angle.group(1) if angle else None,
                                  "count": int(count.group(1)) if count else None}
                else:
                    size, length = WELD_SIZE.search(raw), WELD_LENGTH.search(raw)
                    attributes = {"size": size.group(1).replace(" ", "") if size else None,
                                  "length": length.group(1) if length else None,
                                  "length_unit": length.group(2) if length else None}
                features.append({
                    "schema": "axiom.fabrication_feature.v1",
                    "process": process,
                    "attributes": attributes,
                    "source": filename, "page": page,
                    "region": "full page", "raw_callout": raw,
                    "status": "proposed", "needs_review": True,
                })
    return features


# Explicit flat-pattern dimensions are evidence, not a reconstructed CAD outline.
# Only accept clearly labeled notes, never two incidental dimensions on a print.
FLAT_NOTE = re.compile(
    r"\b(?:FLAT\s+PATTERN|FLAT\s+SIZE|BLANK\s+SIZE)\s*(?:DIMENSIONS?|SIZE)?\s*[:=]?\s*"
    r"(\d+(?:\.\d+)?|\.\d+)\s*[xX×]\s*(\d+(?:\.\d+)?|\.\d+)"
    r"(?:\s*(IN(?:CH(?:ES)?)?|MM|MILLIMETERS?|\"))?",
    re.I,
)


def extract_flat_pattern_candidates(regions, filename):
    """Source-backed labeled rectangular dimensions; units require human review."""
    seen, candidates = set(), []
    for region in regions:
        if region.get("region") != "full page":
            continue
        for line in region.get("text", "").splitlines():
            match = FLAT_NOTE.search(line)
            if not match:
                continue
            units = (match.group(3) or "").upper()
            key = (region.get("page"), line.strip().casefold())
            if key in seen:
                continue
            seen.add(key)
            candidates.append({
                "schema": "ezstimate.flat_note_candidate.v1",
                "length": match.group(1), "width": match.group(2),
                "unit": "mm" if units.startswith(("MM", "MILLI")) else ("in" if units else None),
                "source": filename, "page": region.get("page"),
                "region": region.get("region"),
                "raw_callout": line.strip(), "status": "proposed",
                "needs_review": True,
            })
    return candidates
