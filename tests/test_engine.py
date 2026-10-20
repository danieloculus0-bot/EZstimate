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


class SpatialDrawingRegressionTests(unittest.TestCase):
    """Public synthetic layouts; customer drawings are never checked in."""
    def fake_print(self, material=True, bom=False):
        import fitz
        doc=fitz.open()
        page=doc.new_page(width=792,height=612)
        for x,y,s,size in [(715,498,"REV",5),(726,498,"C",7),
                           (704,520,"NO",5),(714,520,"987654",9),
                           (638,498,"MATL",5)]:
            page.insert_text((x,y),s,fontsize=size)
        if material:
            page.insert_text((654,498),"MFX5000",fontsize=7)
        else:
            page.insert_text((450,432),"QUALITY MATL NO QC2003",fontsize=9)
        if bom:
            for x,s in [(537,"ITEM"),(549,"QTY"),(573,"PART"),
                        (621,"DESCRIPTION"),(729,"MATRL")]:
                page.insert_text((x,85),s,fontsize=5)
            for y,item,qty,part,description in [(90,"1","2","P-101","TUBE SQUARE"),
                                                (96,"2","4","P-102","BRACKET PLATE")]:
                for x,s in [(540,item),(551,qty),(570,part),
                            (603,description),(728,"MFX5000")]:
                    page.insert_text((x,y),s,fontsize=5)
        data=doc.tobytes()
        doc.close()
        return data

    def test_labeled_lower_right_titleblock(self):
        result=inspect_document("fictional_print.pdf",self.fake_print())
        self.assertEqual(result["fields"]["part_number"]["value"],"987654")
        self.assertEqual(result["fields"]["revision"]["value"],"C")
        self.assertEqual(result["fields"]["material"]["value"],"MFX5000")
        self.assertTrue(result["fields"]["material"]["needs_review"])

    def test_unlabeled_quality_note_does_not_become_material(self):
        result=inspect_document("fictional_print.pdf",self.fake_print(material=False))
        self.assertNotIn("material",result["fields"])

    def test_spatial_bom_import_marks_rows_for_review(self):
        result=inspect_document("fictional_bom.pdf",self.fake_print(bom=True))
        self.assertGreaterEqual(len(result["bom"]),2)
        self.assertEqual(result["bom"][0]["quantity"],2)
        self.assertTrue(all(row["needs_review"] for row in result["bom"]))


if __name__ == "__main__":
    unittest.main()
