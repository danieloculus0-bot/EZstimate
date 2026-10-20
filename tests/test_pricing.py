"""Price memory and market pressure regression tests use synthetic values only."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ezstimate.pricing import (
    remember_price, price_history, record_market_signal, market_pressure
)
from ezstimate.bean import journal_market_review
from ezstimate.server import app


class PricingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "pricing.db"
        self.context = patch.dict(os.environ, {"EZSTIMATE_PRICE_DB": str(self.path)})
        self.context.start()

    def tearDown(self):
        self.context.stop()
        self.temp.cleanup()

    @staticmethod
    def price(**changes):
        return {
            "material_key": "sht-stl-0250x60x120-a36-hr",
            "supplier": "Example Metals",
            "source_type": "invoice",
            "source_ref": "INV-001",
            "effective_date": "2026-01-02",
            "unit_price": "220.25",
            "price_unit": "sheet",
            "quantity": "12",
            "currency": "USD",
            **changes,
        }

    def test_each_operation_releases_local_db_file(self):
        # Immediate unlink is intentionally checked on Windows, where unlike
        # Unix an open sqlite handle causes WinError 32.
        from ezstimate.pricing import _connect
        remember_price(self.price())
        price_history("SHT-STL-0250X60X120-A36-HR", "sheet",
                      as_of="2026-02-20")
        with _connect(self.path) as connection:
            mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            self.assertEqual(mode.lower(), "delete")
        self.path.unlink()
        self.assertFalse(self.path.exists())

    def test_history_survives_database_reopen(self):
        saved = remember_price(self.price())
        self.assertTrue(saved["new"])
        self.assertTrue(self.path.exists())
        observed = price_history("SHT-STL-0250X60X120-A36-HR", "sheet",
                                 as_of="2026-02-20")
        self.assertEqual(observed["candidate"]["unit_price"], "220.25")
        self.assertEqual(observed["candidate"]["source_ref"], "INV-001")
        self.assertFalse(observed["auto_applied"])
        self.assertIsNone(price_history("SHT-STL-0250X60X120-A36-HR", "lb",
                                        as_of="2026-02-20")["candidate"])
        self.assertIsNone(price_history("SHT-STL-0250X60X120-A1018-HR", "sheet",
                                        as_of="2026-02-20")["candidate"])

    def test_duplicate_is_idempotent_conflict_rejected(self):
        self.assertTrue(remember_price(self.price())["new"])
        self.assertFalse(remember_price(self.price())["new"])
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            remember_price(self.price(unit_price="225.00"))
        self.assertEqual(len(price_history("SHT-STL-0250X60X120-A36-HR","sheet",
                                           as_of="2026-02-20")["history"]), 1)

    def test_invalid_prices_are_rejected(self):
        for field, value in [("unit_price","-1"),("unit_price","NaN"),
                             ("quantity","0"),("price_unit","ton"),
                             ("currency","EUR"),("effective_date","not-a-date")]:
            with self.subTest(field=field,value=value), self.assertRaises(ValueError):
                remember_price(self.price(**{field:value}))

    def test_history_as_of_never_peeks_forward(self):
        remember_price(self.price(effective_date="2026-03-05"))
        self.assertIsNone(price_history("SHT-STL-0250X60X120-A36-HR","sheet",
                                        as_of="2026-02-20")["candidate"])

    @staticmethod
    def signal(series,value,day,source="Synthetic published reading"):
        return {"series":series, "value":value,"effective_date":day,"source":source}

    def test_market_spike_watch_is_evidence_not_quote_markup(self):
        for series,points in (("diesel_usd_per_gallon",("3.00","3.40")),
                              ("steel_market_index",("100","112"))):
            for day,value in zip(("2026-01-01","2026-01-15"),points):
                record_market_signal(self.signal(series,value,day))
        report = market_pressure("steel",as_of="2026-01-20")
        self.assertEqual(report["risk"], "high")
        self.assertTrue(report["spike_watch"])
        self.assertIsNone(report["forecasted_price"])
        self.assertFalse(report["auto_applied_to_quote"])
        self.assertEqual(report["comparison_series"],2)
        self.assertEqual(market_pressure("aluminum",as_of="2026-01-20")["risk"],
                         "elevated")  # diesel alone is a cross-family freight signal

    def test_stale_market_series_no_longer_scores_pressure(self):
        for day,value in (("2026-01-01","100"),("2026-01-15","115")):
            record_market_signal(self.signal("steel_market_index",value,day))
        result = market_pressure("steel",as_of="2026-07-15")
        self.assertEqual(result["pressure_score"],0)
        self.assertEqual(next(x for x in result["factors"]
                              if x["series"]=="steel_market_index")["status"],"stale")

    def test_no_signal_means_insufficient_not_low_risk(self):
        report=market_pressure("steel",as_of="2026-01-20")
        self.assertEqual(report["risk"],"insufficient")
        self.assertEqual(report["comparison_series"],0)

    def test_market_core_admits_disconnection(self):
        with patch.dict(os.environ, {"EZSTIMATE_BEAN_DB":""}):
            result=journal_market_review(market_pressure("steel"))
        self.assertFalse(result["connected"])

    def test_flask_pricebook_endpoints_retain_real_source(self):
        with app.test_client() as client:
            response=client.post("/api/pricing/prices",json=self.price())
            self.assertEqual(response.status_code,201)
            response=client.get("/api/pricing/prices",query_string={
                "material_key":"SHT-STL-0250X60X120-A36-HR","price_unit":"sheet"})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json["candidate"]["source_ref"],"INV-001")
            response=client.post("/api/pricing/signals",
                json=self.signal("diesel_usd_per_gallon","3.40","2026-01-15"))
            self.assertEqual(response.status_code,201)
            pressure=client.get("/api/pricing/pressure",query_string={"family":"steel"})
            self.assertEqual(pressure.status_code,200)
            self.assertIsNone(pressure.json["forecasted_price"])
            self.assertTrue(client.get("/api/pricing/status").json["price_memory"]=="persistent")


if __name__ == "__main__":
    unittest.main()
