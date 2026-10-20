"""Offline official-feed parser tests. No network or real prices are used."""
from datetime import date
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ezstimate.market_feeds import (parse_bls, parse_eia, refresh_official_feeds,
                                  FeedError, DIESEL_SERIES, SOURCES)
from ezstimate.pricing import market_pressure
from ezstimate.server import app


def bls_response(series, amount="118"):
    return {
        "status": "REQUEST_SUCCEEDED",
        "Results": {"series": [{"seriesID": series, "data": [
            {"year":"2026", "period":"M02", "value":amount,"footnotes":[{"code":"P"}]},
            {"year":"2026", "period":"M01", "value":"100","footnotes":[]},
            {"year":"2025", "period":"M13", "value":"999","footnotes":[]},
        ]}]}
    }


def eia_response(value="4.00"):
    return {"response":{"data":[
        {"period":"2026-02-09","series":DIESEL_SERIES,"value":value},
        {"period":"2026-02-02","series":DIESEL_SERIES,"value":"3.50"},
        {"period":"2026-02-09","series":"EMM_WRONG","value":"999"},
    ]}}


class OfficialFeedsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "market.db")
        self.patch = patch.dict(os.environ, {"EZSTIMATE_PRICE_DB":self.db}, clear=False)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def fake_fetch(self, url):
        if "api.bls.gov" in url:
            series=url.split("/")[-1]
            return bls_response(series)
        if "api.eia.gov" in url:
            self.assertIn("api_key=fixture-key", url)
            return eia_response()
        raise AssertionError("unexpected URL")

    def test_bls_uses_only_monthly_exact_requested_series(self):
        records = parse_bls(bls_response("WPU1017"),"WPU1017",today=date(2026,3,1))
        self.assertEqual(len(records),2)
        self.assertEqual(records[0]["effective_date"],"2026-02-01")
        self.assertEqual(records[0]["value"],"118")
        self.assertIn("provisional",records[0]["notes"])
        with self.assertRaises(FeedError):
            parse_bls(bls_response("OTHER"),"WPU1017")

    def test_eia_filters_incorrect_series(self):
        records = parse_eia(eia_response(),today=date(2026,3,1))
        self.assertEqual(len(records),2)
        self.assertEqual(records[0]["value"],"4.00")
        self.assertEqual(records[0]["effective_date"],"2026-02-09")

    def test_refresh_imports_bls_and_eia_and_preserves_quotes(self):
        result=refresh_official_feeds(fetch_json=self.fake_fetch,
                                      eia_key="fixture-key",today=date(2026,3,1))
        self.assertEqual(result["status"],"ok")
        self.assertEqual(result["saved"],6)
        self.assertFalse(result["auto_quote_change"])
        self.assertEqual(result["providers"]["BLS:WPU1017"]["series"],"WPU1017")
        self.assertEqual(result["providers"]["BLS:WPU102501"]["series"],"WPU102501")
        self.assertEqual(result["providers"]["EIA:diesel"]["series"],DIESEL_SERIES)
        second=refresh_official_feeds(fetch_json=self.fake_fetch,
                                      eia_key="fixture-key",today=date(2026,3,1))
        self.assertEqual(second["saved"],0)
        self.assertEqual(second["unchanged"],6)
        watch=market_pressure("steel",as_of="2026-03-01")
        self.assertEqual(watch["risk"],"high")
        self.assertIsNone(watch["forecasted_price"])

    def test_no_eia_key_is_explicit_not_a_fake_zero(self):
        j=refresh_official_feeds(fetch_json=self.fake_fetch,eia_key="",
                                 today=date(2026,3,1))
        self.assertEqual(j["providers"]["EIA:diesel"]["status"],"not_configured")
        self.assertEqual(j["saved"],4)

    def test_bls_revision_is_not_silently_overwritten(self):
        refresh_official_feeds(fetch_json=self.fake_fetch,eia_key="",
                               today=date(2026,3,1))
        def changed(url):
            series=url.split("/")[-1]
            return bls_response(series,"130")
        result=refresh_official_feeds(fetch_json=changed,eia_key="",
                                      today=date(2026,3,1))
        self.assertEqual(result["conflicts"],2)
        self.assertEqual(result["saved"],0)

    def test_network_provider_failure_returns_partial_not_fabricated_prices(self):
        def partial(url):
            if "WPU102501" in url:
                raise FeedError("synthetic provider outage")
            return self.fake_fetch(url)
        result=refresh_official_feeds(fetch_json=partial,eia_key="",
                                      today=date(2026,3,1))
        self.assertEqual(result["status"],"partial")
        self.assertEqual(result["providers"]["BLS:WPU102501"]["status"],"error")

    def test_local_status_does_not_reveal_credentials(self):
        with patch.dict(os.environ,{"EIA_API_KEY":"test-should-not-be-sent-to-browser"}):
            with app.test_client() as client:
                data=client.get("/api/pricing/feeds/status")
                self.assertTrue(data.json["eia_key_configured"])
                self.assertNotIn("test-should-not-be-sent-to-browser",data.get_data(as_text=True))
                self.assertEqual(data.json["bls_series"]["steel_market_index"],"WPU1017")


if __name__ == "__main__":
    unittest.main()
