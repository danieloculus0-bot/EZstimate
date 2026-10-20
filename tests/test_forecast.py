"""Synthetic frozen prospective hypotheses and invoice outcome scorecard tests."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ezstimate.pricing import remember_price, record_market_signal
from ezstimate.forecast import freeze_forecast, evaluate_forecasts
from ezstimate.server import app
from ezstimate.bean import journal_forecast_assessment


class PriceForecastTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name)/"forecast.db")
        self.patch = patch.dict(os.environ,{"EZSTIMATE_PRICE_DB":self.path},clear=False)
        self.patch.start()
        self.invoice("INV-BASE", "2026-01-15", "100")
        for signal in ("steel_market_index","diesel_usd_per_gallon"):
            start,finish=("100","115") if signal=="steel_market_index" else ("3.00","3.50")
            record_market_signal({"series":signal,"value":start,"effective_date":"2026-01-01",
                                  "source":"synthetic_observation"})
            record_market_signal({"series":signal,"value":finish,"effective_date":"2026-02-01",
                                  "source":"synthetic_observation"})

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def invoice(self, ref,day,value,*,supplier="Fictional Supplier",qty="12"):
        return remember_price({
            "material_key":"SHT-STL-0250X60X120-A36-HR",
            "supplier":supplier,"source_type":"invoice","source_ref":ref,
            "effective_date":day,"unit_price":value,"price_unit":"sheet",
            "quantity":qty,"currency":"USD"})

    def snapshot(self, **changes):
        return {
            "material_key":"SHT-STL-0250X60X120-A36-HR",
            "supplier":"Fictional Supplier",
            "price_unit":"sheet","quantity":"12",
            "material_family":"steel","horizon_days":30,
            "spike_threshold_pct":"5", **changes}

    def test_frozen_warning_and_later_invoice_gives_real_hit(self):
        created=freeze_forecast(self.snapshot(),issue_date="2026-02-05")
        self.assertTrue(created["new"])
        self.assertEqual(created["record"]["risk"],"high")
        self.assertEqual(created["record"]["baseline_price"],"100")
        still=freeze_forecast(self.snapshot(),issue_date="2026-02-05")
        self.assertFalse(still["new"])
        self.invoice("INV-LATER","2026-02-20","110")
        pending=evaluate_forecasts(as_of="2026-02-25")
        self.assertEqual(pending["pending"],1)
        self.assertIsNone(pending["samples"][0]["actual_spike"])
        mature=evaluate_forecasts(as_of="2026-03-15")
        self.assertEqual(mature["evaluated"],1)
        self.assertEqual(mature["correct"],1)
        self.assertEqual(mature["accuracy"],"100.0")
        self.assertEqual(mature["always_no_spike_baseline_accuracy"],"0.0")
        self.assertEqual(mature["samples"][0]["outcome_invoice"]["source_ref"],"INV-LATER")
        self.assertFalse(mature["sufficient_to_validate"])

    def test_missing_invoice_not_misclassified_as_wrong_prediction(self):
        freeze_forecast(self.snapshot(),issue_date="2026-02-05")
        report=evaluate_forecasts(as_of="2026-04-01")
        self.assertEqual(report["evaluated"],0)
        self.assertEqual(report["unobserved"],1)
        self.assertIsNone(report["accuracy"])

    def test_different_supplier_or_quantity_never_counts(self):
        freeze_forecast(self.snapshot(),issue_date="2026-02-05")
        self.invoice("NOT-OUR-SUPPLIER","2026-02-20","180",supplier="Different Supplier")
        self.invoice("NOT-OUR-QUANTITY","2026-02-20","180",qty="3")
        report=evaluate_forecasts(as_of="2026-04-01")
        self.assertEqual(report["evaluated"],0)
        self.assertEqual(report["unobserved"],1)

    def test_unavailable_baseline_blocks_freeze(self):
        with self.assertRaisesRegex(ValueError,"historical verified invoice"):
            freeze_forecast(self.snapshot(supplier="Unpriced Supplier"),
                            issue_date="2026-02-05")

    def test_outcomes_must_be_added_after_hypothesis(self):
        # This source is dated after the fictional issue date, but existed in
        # the database before the hypothesis was created: cannot pass as a win.
        self.invoice("INV-ALREADY-KNOWN","2026-02-20","150")
        freeze_forecast(self.snapshot(),issue_date="2026-02-05")
        report=evaluate_forecasts(as_of="2026-04-01")
        self.assertEqual(report["evaluated"],0)
        self.assertEqual(report["unobserved"],1)

    def test_rest_endpoint_cannot_backdate_prediction(self):
        with app.test_client() as client:
            payload=self.snapshot()
            payload["issue_date"]="2026-02-05"
            response=client.post("/api/pricing/forecasts",json=payload)
            self.assertEqual(response.status_code,201)
            self.assertNotEqual(response.json["record"]["issued_date"],"2026-02-05")
            card=client.get("/api/pricing/forecasts")
            self.assertEqual(card.status_code,200)
            self.assertEqual(card.json["pending"],1)

    def test_real_bean_journal_disconnected_is_truthful(self):
        with patch.dict(os.environ,{"EZSTIMATE_BEAN_DB":""}):
            r=journal_forecast_assessment(evaluate_forecasts(as_of="2026-04-01"))
        self.assertFalse(r["connected"])


if __name__=="__main__":
    unittest.main()
