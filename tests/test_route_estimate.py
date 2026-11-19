"""Synthetic acceptance tests for the explicit-rate routing CLI."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ezstimate.route_estimate import estimate

class RoutingAcceptance(unittest.TestCase):
    def setUp(self):
        self.spec = {"quantity": 10, "material_each": 20, "scrap_percent": 20, "gross_margin_percent": 25, "operations": [
            {"process": "laser", "length_mm": 100, "rate_per_unit": "0.02", "setup_cost": 10},
            {"process": "brake", "bends": 2, "rate_per_unit": 3, "setup_cost": 20}]}
    def test_reconciled_quote(self):
        result = estimate(self.spec)
        self.assertEqual(result["material_with_scrap_each"], "25.00")
        self.assertEqual(result["routing_cost_each"], "11.00")
        self.assertEqual(result["cost_total"], "360.00")
        self.assertEqual(result["sell_total"], "480.00")
    def test_no_missing_rates(self):
        del self.spec["operations"][0]["rate_per_unit"]
        with self.assertRaises(ValueError):
            estimate(self.spec)
    def test_reject_invalid_margin(self):
        self.spec["gross_margin_percent"] = 100
        with self.assertRaises(ValueError):
            estimate(self.spec)
    def test_reject_unknown_process(self):
        self.spec["operations"][0]["process"] = "magic"
        with self.assertRaises(ValueError):
            estimate(self.spec)
    def test_reject_negative_or_nonfinite(self):
        self.spec["material_each"] = "-1"
        with self.assertRaises(ValueError):
            estimate(self.spec)
        self.spec["material_each"] = "NaN"
        with self.assertRaises(ValueError):
            estimate(self.spec)
    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "synthetic.json"
            p.write_text(json.dumps(self.spec), encoding="utf-8")
            proc = subprocess.run([sys.executable, "-m", "ezstimate.route_estimate", str(p)], capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(proc.stdout)["sell_total"], "480.00")

if __name__ == "__main__":
    unittest.main()
