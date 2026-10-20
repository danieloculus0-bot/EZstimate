# EZstimate

### [OPEN THE INTERACTIVE EZSTIMATE DEMO](https://danieloculus0-bot.github.io/EZstimate/)

[Demo deployment and tests](https://github.com/danieloculus0-bot/EZstimate/actions/workflows/pages.yml) · [Demo source](web/demo.html) · [Full repository](https://github.com/danieloculus0-bot/EZstimate)

**Browser demo:** Load a synthetic RFQ, upload selectable-text PDF drawings and POs, import a CSV BOM, identify material and revision conflicts, enter manufacturing costs, calculate a draft quote, and view BEAN-style local review findings. The browser demo is separate from the Python application and does **not** invoke a live BEAN Core or ERP connector. The deployment workflow must pass for GitHub Pages to serve the site.


**Manufacturing estimating workbench · engineering suite · experimental alpha**

EZstimate is a local-first manufacturing quote tool. It accepts customer drawings, BOMs, and purchase-order PDFs, proposes traceable fields for human review, calculates quotes from explicitly provided costs, and can journal reviewed observations into **real BEAN Core** when that installation is available. It does not invent material prices, process times, or approval decisions.

The interface uses the BEAN green / charcoal shared engineering-suite theme. See `docs/ARCHITECTURE.md` for ForgeVault, Axiom, and BEAN boundaries.

## Price Memory + Material Forecast (new local module)

EZstimate now remembers verified, dated material prices from supplier quotes, purchase orders and invoices using a **persistent local SQLite database**. Search by exact ERP material key and unit; see supplier/source/age, and explicitly copy a matching **per-each** price into a draft quote line. Other purchase units require a real per-part yield conversion before pricing.

The new **Material Forecast** panel stores dated diesel, steel/aluminum indexes, supplier lead days and sourced sentiment readings and generates transparent **market-pressure watches**. It does not invent future material prices or silently raise a customer's quote. The optional **real BEAN Core** bridge can journal these market observations for later evidence-based outcome checking; model inference and forecast learning are not claimed yet.

The old MID JobBOSS material-demand/shortage/need-date data is now supported by a **read-only XLSX preview adapter** in the local workbench: select your MID workbook to examine demand events, risk flags, and buy-now actions. That preview does not automatically populate quote prices, persist forecast quantities, or write to ERP. Market readings are **manual** for now; there is no live EIA/BLS refresh yet.

**These persistent functions run only in the [local Python build](#quickstart). GitHub Pages remains a static browser demo without a private price database.** Full [data contract and roadmap](docs/MATERIAL_INTELLIGENCE.md).

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

## Verified engineering-suite wiring (2026-10-20)

The independently packaged estimating engine now has a tested local handoff to Axiom Beta: the real ForgeVault release service supplies checksum-verified PDF bytes and a specific version/package; EZstimate extracts revision/material candidates and computes explicit-cost draft pricing; the Axiom importer independently recomputes the quoted total and retains the exact source version, digest and itemized quote evidence. Axiom's Quoting screen displays the linked drawing and revision identifiers. The BEAN observation is recorded using EZstimate's actual optional BEAN Core journal interface.

[Cross-platform integration workflow](https://github.com/danieloculus0-bot/Axiom_Beta/actions/workflows/ezstimate-suite-wiring.yml) passed on Windows and Linux and [Axiom PR #16](https://github.com/danieloculus0-bot/Axiom_Beta/pull/16) merged. The Axiom importer is a local Python API, not an unauthenticated shop-network connector or an automatic quote approval. This implementation also shares the BEAN Gothic Lime design tokens (charcoal #0F1113 and lime #79DE4B) while keeping quote arithmetic separate from BEAN reasoning.

## Real-print-informed validation, customer documents kept private

Three existing user-supplied customer drawings were used only for **private**
diagnostics: a dimensioned plate, a welded skid with a multi-row BOM, and a
formed/welded enclosure. The public regression suite contains entirely
fictional part numbers/material keys and synthetic PDF geometry, **not**
customer drawing files, identifiers, instructions or geometry.

Title-block numbers, revisions and material identifiers are now proposed
using labeled **spatial proximity**; column-aligned BOM rows can be proposed
when text-order and PDF table extraction fail. These are *review-required
candidates*, never approvals or automatically verified material grades.
Actual costs and shop processing times must still come from approved sources.
