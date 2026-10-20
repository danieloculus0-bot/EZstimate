import hashlib
import unittest
from io import BytesIO
from ezstimate.core import analyze_pdf, import_bom, calculate_quote, quote_proposal
from ezstimate.server import HTML

INPUTS={"quantity":10,"material_unit_cost":"20","labor_hours_per_unit":"0.5",
        "labor_rate_per_hour":"60","setup_hours":"2","setup_rate_per_hour":"80",
        "outside_unit_cost":"5","scrap_rate":"0.1","overhead_rate":"0.15","margin_rate":"0.25"}

class EstimationTests(unittest.TestCase):
    def test_explicit_quote_math(self):
        price=calculate_quote(INPUTS)
        self.assertEqual(price["quoted_unit_price"],"112.27")
        self.assertEqual(price["quoted_total"],"1122.74")
    def test_missing_inputs_not_assumed(self):
        with self.assertRaisesRegex(ValueError,"missing explicit costs"):
            calculate_quote({"quantity":10})
        for k,v in (("quantity",0),("scrap_rate","1"),("margin_rate","1"),
                    ("overhead_rate","NaN"),("material_unit_cost","-1")):
            with self.subTest(field=k):
                with self.assertRaises(ValueError):calculate_quote(dict(INPUTS,**{k:v}))
    def test_real_pdf_title_material_po(self):
        import fitz
        doc=fitz.open();p=doc.new_page()
        for idx,line in enumerate(("MATERIAL: ASTM A36 HOT ROLLED STEEL","DWG NO: 02250244-100","PO #: ABC-900","QTY: 20")):
            p.insert_text((40,70+idx*25),line)
        pdf=doc.tobytes();doc.close()
        result=analyze_pdf(pdf,filename="source.pdf")
        self.assertEqual(result["sha256"],hashlib.sha256(pdf).hexdigest())
        self.assertIn("ASTM A36 HOT ROLLED STEEL",[x["value"] for x in result["candidates"] if x["kind"]=="material"])
        self.assertTrue(all(x["review_required"] for x in result["candidates"]))
        self.assertEqual(quote_proposal("Q-1",INPUTS,drawing=result)["status"],"review_required")
    def test_scanned_not_mislabeled_as_ocr(self):
        import fitz
        doc=fitz.open();doc.new_page();pdf=doc.tobytes();doc.close()
        self.assertIn("OCR required",analyze_pdf(pdf)["warnings"][0])
    def test_bom_csv_and_xlsx(self):
        rows=import_bom(b"Part Number,Qty\nA-10,4\nB-20,2\n",filename="parts.csv")
        self.assertEqual(rows["rows"][1]["row"],3)
        from openpyxl import Workbook
        w=Workbook();w.active.append(["Part Number","Qty"]);w.active.append(["A-10",4])
        data=BytesIO();w.save(data)
        book=import_bom(data.getvalue(),filename="parts.xlsx")
        self.assertEqual(book["rows"][0]["cells"]["Qty"],"4")
    def test_release_hash_mismatch(self):
        with self.assertRaisesRegex(ValueError,"SHA"):
            quote_proposal("Q-1",INPUTS,drawing={"sha256":"a"},
                           released_drawing={"sha256":"b","lifecycle":"Released","file_version_id":"x"})
    def test_real_ui_actions_and_palette(self):
        for token in ("--accent:#79DE4B","/api/pdf","/api/bom","/api/quote","/api/bean","REVIEW REQUIRED"):
            self.assertIn(token,HTML)
