"""Synthetic effective-date and rate-provenance acceptance tests."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from ezstimate.rate_book import resolve


class RateBookAcceptance(unittest.TestCase):
    def setUp(self):
        self.route = {"quantity": 2, "material_each": 10, "currency": "USD",
                      "operations": [{"process": "laser", "length_mm": 100}]}
        self.book = {"version": "synthetic-v1", "currency": "USD", "rates": [
            {"process": "laser", "unit": "length_mm", "rate_per_unit": "0.02",
             "effective_from": "2026-01-01", "effective_to": "2026-06-30"},
            {"process": "laser", "unit": "length_mm", "rate_per_unit": "0.03",
             "effective_from": "2026-07-01"}]}

    def test_effective_rate_and_provenance(self):
        result = resolve(self.route, self.book, "2026-08-01")
        self.assertEqual(result["cost_total"], "26.00")
        self.assertEqual(result["rate_provenance"][0]["rate_book_index"], 1)
        self.assertEqual(result["rate_book_version"], "synthetic-v1")

    def test_old_period(self):
        self.assertEqual(resolve(self.route, self.book, "2026-05-01")["cost_total"], "24.00")

    def test_gap_fails_closed(self):
        self.book["rates"][1]["effective_from"] = "2027-01-01"
        with self.assertRaisesRegex(ValueError, "expected one"):
            resolve(self.route, self.book, "2026-08-01")

    def test_overlap_fails_closed(self):
        self.book["rates"][0]["effective_to"] = "2026-12-31"
        with self.assertRaisesRegex(ValueError, "found 2"):
            resolve(self.route, self.book, "2026-08-01")

    def test_currency_mismatch(self):
        self.book["currency"] = "EUR"
        with self.assertRaisesRegex(ValueError, "currencies"):
            resolve(self.route, self.book, "2026-08-01")

    def test_inline_rate_rejected(self):
        self.route["operations"][0]["rate_per_unit"] = 1
        with self.assertRaisesRegex(ValueError, "conflicts"):
            resolve(self.route, self.book, "2026-08-01")

    def test_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            route = Path(directory) / "route.json"
            book = Path(directory) / "rates.json"
            route.write_text(json.dumps(self.route), encoding="utf-8")
            book.write_text(json.dumps(self.book), encoding="utf-8")
            run = subprocess.run([sys.executable, "-m", "ezstimate.rate_book",
                                  str(route), str(book), "--as-of", "2026-08-01"],
                                 capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(run.stdout)["cost_total"], "26.00")


if __name__ == "__main__":
    unittest.main()
