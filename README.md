# EZstimate

**Manufacturing estimating workbench · engineering suite · experimental alpha**

EZstimate is a local-first manufacturing quote tool. It accepts customer drawings, BOMs, and purchase-order PDFs, proposes traceable fields for human review, calculates quotes from explicitly provided costs, and can journal reviewed observations into **real BEAN Core** when that installation is available. It does not invent material prices, process times, or approval decisions.

The interface uses the BEAN green / charcoal shared engineering-suite theme. See `docs/ARCHITECTURE.md` for ForgeVault, Axiom, and BEAN boundaries.

## Quickstart

```bash
python -m pip install -e .
python -m ezstimate.server
```

Open http://127.0.0.1:8765. For PDF uploads, PyMuPDF is required and installed with the package; scanned image-only drawings require separate OCR and are flagged rather than silently assumed. Spreadsheet BOMs require openpyxl.

To persist quote observations into an **installed BEAN Core**, set `EZSTIMATE_BEAN_DB` to a local BEAN SQLite path and ensure `bean` is importable in the same Python environment, then run the server. Without both, the UI explicitly labels the review **local checks only**.

```bash
python -m unittest discover -s tests -v
```

## Scope

- PDF title-block, material, drawing, and PO candidate extraction with page and region references
- CSV/XLSX BOM import with row-level provenance
- Explicit numeric pricing inputs, quantity handling, scrap, shop labor, outside services, setup, gross-margin pricing
- Missing-cost and document-conflict warnings with review status, never simulated confidence
- Local BEAN Core journal connection if the real module is available (not a pretend generative assistant)

**Not yet:** OCR, fully automatic table recognition for arbitrary drawing formats, validated manufacturer pricing, connected historical ERP costs, PO acceptance, vendor purchasing, CAD mass estimation, or released quote authorization. All extracted fields need human review, especially tolerances and processes. Public fixtures and tests are synthetic; never commit customer drawings, prices, or POs.
