import io
import os
import unittest
from unittest.mock import patch
from ezstimate.engine import inspect_document, price_quote, review_package
from ezstimate.bean import local_review, journal

class EstimateTests(unittest.TestCase):
    def test_bom_provenance(self):
        doc = inspect_document("assembly.csv",
            b"Part Number,Qty,Description,Material,Rev\nBR-22,4,Bracket,A36,B\n")
        self.assertEqual(doc["kind"], "bom")
        self.assertEqual(doc["bom"][0]["quantity"], 4)
        self.assertEqual(doc["bom"][0]["row"], 2)
        self.assertTrue(doc["bom"][0]["needs_review"])

    def test_margin_not_markup(self):
        q = price_quote({"lines": [{"part_number": "BR-22", "quantity": 4,
            "material_cost_each": 10, "labor_hours_each": .5,
            "shop_rate_per_hour": 60, "outside_cost_each": 5,
            "setup_cost_total": 20, "scrap_pct": 10, "margin_pct": 20}]})
        self.assertEqual(q["total"], "255.00")
        self.assertEqual(q["lines"][0]["unit_sell"], "63.75")
        self.assertEqual(q["approval"], "not approved")

    def test_missing_cost_blocks_quote(self):
        q = price_quote({"lines": [{"part_number": "BR-22", "quantity": 3,
                                    "labor_hours_each": 1, "shop_rate_per_hour": 60}]})
        self.assertIsNone(q["total"])
        self.assertIn("material cost missing", q["issues"][0])

    def test_bad_costs_block(self):
        normal = {"part_number": "P", "quantity": 1, "material_cost_each": 10,
                  "labor_hours_each": 0}
        for change in ({"quantity": 0}, {"quantity": 1.5},
                       {"material_cost_each": "-1"}, {"material_cost_each": "NaN"},
                       {"margin_pct": 100}, {"scrap_pct": 150}):
            self.assertEqual(price_quote({"lines": [{**normal, **change}]})["status"], "incomplete")

    def test_mismatched_revisions(self):
        docs = [{"filename": "drawing.pdf", "fields": {"revision": {"value": "A", "source": "drawing.pdf"}}},
                {"filename": "po.pdf", "fields": {"revision": {"value": "B", "source": "po.pdf"}}}]
        self.assertTrue(any(i["field"] == "revision" for i in review_package(docs)))

    def test_non_bean_advice_labeled(self):
        result = local_review([], price_quote({"lines": []}))
        self.assertFalse(result["bean_core_invoked"])
        self.assertIn("local", result["engine"])

    def test_no_bean_db_does_not_claim_connection(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(journal([], price_quote({}), local_review([], price_quote({})))["connected"])

    def test_pdf_text_and_title_block(self):
        import fitz
        pdf = fitz.open()
        p = pdf.new_page(width=600, height=800)
        p.insert_text((330, 600), "MATERIAL: ASTM A36")
        p.insert_text((330, 620), "PART NO: PR-100")
        p.insert_text((330, 640), "REV: B")
        result = inspect_document("drawing.pdf", pdf.tobytes())
        pdf.close()
        self.assertEqual(result["fields"]["material"]["value"], "ASTM A36")
        self.assertEqual(result["fields"]["revision"]["value"], "B")
        self.assertEqual(result["fields"]["material"]["region"], "lower-right title block")

if __name__ == "__main__":
    unittest.main()
