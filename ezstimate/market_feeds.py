"""Official EIA/BLS data adapters. Network calls occur only when the local operator refreshes.

No public API credentials are sent to browsers. No simulation/fallback market data.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .pricing import record_market_signal

BLS_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
EIA_URL = "https://api.eia.gov/v2/petroleum/pri/gnd/data/"
SOURCES = {
    "steel_market_index": ("WPU1017", "BLS PPI steel mill products"),
    "aluminum_market_index": ("WPU102501", "BLS PPI aluminum mill shapes"),
}
DIESEL_SERIES = "EMD_EPD2D_PTE_NUS_DPG"  # US No. 2 retail diesel, dollars/gal
MAX_RESPONSE_BYTES = 2_000_000


class FeedError(ValueError):
    """A feed failure, distinct from a verified zero or an estimate."""


def _https_json(url):
    if not url.startswith(("https://api.bls.gov/", "https://api.eia.gov/")):
        raise FeedError("Unexpected data provider")
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "EZstimate/0.1 material-intelligence"})
    try:
        with urlopen(req, timeout=12) as response:
            blob = response.read(MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        # Do not include EIA key or the URL in error text.
        raise FeedError("Provider unreachable or rejected the request") from exc
    if len(blob) > MAX_RESPONSE_BYTES:
        raise FeedError("Provider response exceeded allowed size")
    try:
        return json.loads(blob)
    except (ValueError, UnicodeDecodeError) as exc:
        raise FeedError("Provider returned invalid JSON") from exc


def _positive_value(raw):
    try:
        if isinstance(raw, bool):
            raise ValueError()
        value = Decimal(str(raw).replace(",", ""))
        if not value.is_finite() or value <= 0:
            raise ValueError()
        return str(value)
    except (ValueError, InvalidOperation, TypeError):
        raise FeedError("Invalid index or diesel price returned by provider") from None


def parse_bls(payload, series, *, today=None):
    """BLS public API returns monthly PPI records; use first day as period ID.

    PPI reflects the named industry commodity index, not an individual sheet quote.
    """
    cutoff = today or date.today()
    if not isinstance(payload, dict) or payload.get("status") != "REQUEST_SUCCEEDED":
        raise FeedError("BLS did not report a successful response")
    matches = [x for x in payload.get("Results", {}).get("series", [])
               if isinstance(x, dict) and x.get("seriesID") == series]
    if len(matches) != 1:
        raise FeedError("BLS response did not match the requested series")
    rows = []
    for rec in matches[0].get("data", []):
        try:
            year = int(rec["year"])
            period = rec["period"]
            if not isinstance(period, str) or len(period) != 3 or period[0] != "M":
                continue
            month = int(period[1:])
            if not 1 <= month <= 12:  # M13 is BLS annual average, not a month
                continue
            observation_date = date(year, month, 1)
            if observation_date > cutoff:
                continue
            value = _positive_value(rec["value"])
        except (TypeError, ValueError, KeyError, FeedError) as exc:
            if isinstance(exc, FeedError):
                raise
            continue
        preliminary = any(isinstance(f, dict) and f.get("code") == "P"
                          for f in rec.get("footnotes", []))
        rows.append({"effective_date": observation_date.isoformat(), "value": value,
                     "notes": "BLS provisional value" if preliminary else "BLS published monthly PPI"})
    if not rows:
        raise FeedError("BLS returned no valid dated monthly observations")
    return sorted(rows, key=lambda r:r["effective_date"], reverse=True)[:14]


def parse_eia(payload, *, today=None):
    cutoff = today or date.today()
    if not isinstance(payload, dict) or not isinstance(payload.get("response"), dict):
        raise FeedError("EIA did not provide a data response")
    rows = []
    for rec in payload["response"].get("data", []):
        if not isinstance(rec, dict) or rec.get("series") != DIESEL_SERIES:
            continue
        try:
            period = str(rec["period"])
            observed = date.fromisoformat(period)
            if observed > cutoff:
                continue
            value = _positive_value(rec["value"])
        except (TypeError, ValueError, FeedError) as exc:
            if isinstance(exc, FeedError):
                raise
            continue
        rows.append({"effective_date": observed.isoformat(), "value": value,
                     "notes": "EIA weekly US No. 2 retail diesel price (USD/gallon)"})
    if not rows:
        raise FeedError("EIA returned no valid weekly diesel observations for the requested series")
    return sorted(rows, key=lambda r:r["effective_date"], reverse=True)[:16]


def refresh_official_feeds(*, fetch_json=None, eia_key=None, today=None, path=None):
    """Fetch observed market data, not estimates. Resilient to one feed being offline.

    Returns provider-level failures. Revisions that contradict stored period/source
    values remain unresolved instead of overwriting previous records.
    """
    fetch = fetch_json or _https_json
    cutoff = today or date.today()
    if isinstance(cutoff, str):
        cutoff = date.fromisoformat(cutoff)
    result = {"providers": {}, "saved": 0, "unchanged": 0, "conflicts": 0,
              "errors": [], "as_of": cutoff.isoformat(), "auto_quote_change": False}
    for signal, (series_id, label) in SOURCES.items():
        key = "BLS:" + series_id
        try:
            data = parse_bls(fetch(BLS_URL+series_id), series_id, today=cutoff)
            for item in data:
                source = "BLS:PPI:" + series_id
                try:
                    record = record_market_signal({"series":signal,"source":source,**item},path=path)
                    result["saved" if record["new"] else "unchanged"] += 1
                except ValueError:
                    result["conflicts"] += 1
                    result["errors"].append(f"{key}: stored value differs for {item['effective_date']}; review official revision")
            result["providers"][key] = {"status":"ok", "observations":len(data),
                                        "series":series_id,"description":label}
        except (FeedError, ValueError) as exc:
            result["providers"][key] = {"status":"error", "error":str(exc)}
            result["errors"].append(f"{key}: {exc}")
    key = eia_key if eia_key is not None else os.environ.get("EIA_API_KEY", "")
    if not key:
        result["providers"]["EIA:diesel"] = {"status":"not_configured", "series":DIESEL_SERIES,
                                               "hint":"Set EIA_API_KEY in the local environment"}
    else:
        params = urlencode({
            "api_key": key, "frequency":"weekly", "data[0]":"value",
            "facets[series][]":DIESEL_SERIES,
            "sort[0][column]":"period", "sort[0][direction]":"desc",
            "offset":"0", "length":"16",
        })
        try:
            data = parse_eia(fetch(EIA_URL+"?"+params),today=cutoff)
            for item in data:
                try:
                    record = record_market_signal({
                        "series":"diesel_usd_per_gallon",
                        "source":"EIA:petroleum/pri/gnd:"+DIESEL_SERIES, **item},path=path)
                    result["saved" if record["new"] else "unchanged"] += 1
                except ValueError:
                    result["conflicts"] += 1
                    result["errors"].append("EIA:diesel: stored weekly value differs for "+
                                            item["effective_date"]+"; review revision")
            result["providers"]["EIA:diesel"] = {"status":"ok", "observations":len(data),
                                                  "series":DIESEL_SERIES}
        except (FeedError, ValueError) as exc:
            result["providers"]["EIA:diesel"] = {"status":"error","error":str(exc)}
            result["errors"].append("EIA:diesel: "+str(exc))
    result["status"] = "ok" if not result["errors"] else "partial" if result["saved"] or result["unchanged"] else "error"
    result["no_live_bean_inference"] = True
    return result
