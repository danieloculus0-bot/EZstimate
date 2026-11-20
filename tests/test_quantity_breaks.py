"""Synthetic acceptance coverage for quantity-break quote calculations."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ezstimate.quantity_breaks import compare_quantity_breaks


class QuantityBreakAcceptance(unittest.TestCase):
    def setUp(self):
        self.spec = {
            "quantities": [1, 10, 100],
            "route": {
                "material_each": "20",
                "gross_margin_percent": 20,
                "operations": [
                    {"process": "laser", "length_mm": 100,
                     "rate_per_unit": "0.02", "setup_cost": 100}
                ],
            },
        }

    def test_setup_amortization_and_reconciliation(self):
        result = compare_quantity_breaks(self.spec)
        self.assertEqual([x["cost_each"] for x in result["quotes"]],
                         ["122.00", "32.00", "23.00"])
        self.assertEqual([x["sell_each"] for x in result["quotes"]],
                         ["152.50", "40.00", "28.75"])
        self.assertEqual([x["cost_total"] for x in result["quotes"]],
                         ["122.00", "320.00", "2300.00"])
        self.assertEqual(result["lowest_sell_each_quantity"], 100)

    def test_preserves_requested_order(self):
        self.spec["quantities"] = [100, 1]
        result = compare_quantity_breaks(self.spec)
        self.assertEqual([x["quantity"] for x in result["quotes"]], [100, 1])

    def test_rejects_invalid_quantities(self):
        for values in ([], [0], [-2], [1.5], ["NaN"], [True], [2, "2"]):
            with self.subTest(values=values):
                self.spec["quantities"] = values
                with self.assertRaises(ValueError):
                    compare_quantity_breaks(self.spec)

    def test_rejects_conflicting_route_quantity(self):
        self.spec["route"]["quantity"] = 5
        with self.assertRaises(ValueError):
            compare_quantity_breaks(self.spec)

    def test_missing_rate_fails_all_quotes(self):
        del self.spec["route"]["operations"][0]["rate_per_unit"]
        with self.assertRaises(ValueError):
            compare_quantity_breaks(self.spec)

    def test_cli_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.json"
            path.write_text(json.dumps(self.spec), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-m", "ezstimate.quantity_breaks", str(path)],
                text=True, capture_output=True, check=True)
            self.assertEqual(json.loads(proc.stdout)["quotes"][1]["sell_total"], "400.00")


if __name__ == "__main__":
    unittest.main()
