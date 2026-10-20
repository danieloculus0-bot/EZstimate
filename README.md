# EZstimate

### [OPEN THE INTERACTIVE EZSTIMATE DEMO](https://danieloculus0-bot.github.io/EZstimate/)

[Demo deployment and tests](https://github.com/danieloculus0-bot/EZstimate/actions/workflows/pages.yml) · [Demo source](web/demo.html) · [Full repository](https://github.com/danieloculus0-bot/EZstimate)

**Browser demo:** Load a synthetic RFQ, upload selectable-text PDF drawings and POs, import a CSV BOM, identify material and revision conflicts, enter manufacturing costs, calculate a draft quote, and view BEAN-style local review findings. The browser demo is separate from the Python application and does **not** invoke a live BEAN Core or ERP connector. The deployment workflow must pass for GitHub Pages to serve the site.


**Manufacturing estimating workbench · engineering suite · experimental alpha**

EZstimate is a local-first manufacturing quote tool. It accepts customer drawings, BOMs, and purchase-order PDFs, proposes traceable fields for human review, calculates quotes from explicitly provided costs, and can journal reviewed observations into **real BEAN Core** when that installation is available. It does not invent material prices, process times, or approval decisions.

The interface uses the BEAN green / charcoal shared engineering-suite theme. See `docs/ARCHITECTURE.md` for ForgeVault, Axiom, and BEAN boundaries.

## Price Memory + Material Forecast (new local module)

EZstimate now remembers verified, dated material prices from supplier quotes, purchase orders and invoices using a **persistent local SQLite database**. Search by exact ERP material key and unit; see supplier/source/age, and explicitly copy a matching **per-each** price into a draft quote line. Other purchase units require a real per-part yield conversion before pricing.

The new **Material Forecast** panel refreshes **BLS steel and aluminum PPI data** automatically every 24 hours while the local server runs, and **EIA US diesel data** when `EIA_API_KEY` is configured. It also supports manual supplier lead-time and sentiment observations, generating transparent **market-pressure watches**. It does not invent future material prices or silently raise a customer's quote. The optional **real BEAN Core** bridge can journal market observations and the new **frozen forecast-versus-invoice scorecard**, recording hits and misses against later exact-matching invoices. This is evidence-based evaluation, not trained forecasting or automatic price changes.

The old MID JobBOSS material-demand/shortage/need-date data is now supported by a **read-only XLSX preview adapter** in the local workbench: select your MID workbook to examine demand events, risk flags, and buy-now actions. That preview does not automatically populate quote prices, persist forecast quantities, or write to ERP. Market readings can now include official BLS/EIA refreshes in the local build; manual lead-time/sentiment inputs remain available.

**To enable diesel refresh on Windows:** obtain a free [EIA API key](https://www.eia.gov/opendata/register.php), then run `$env:EIA_API_KEY = Read-Host "EIA key"` in PowerShell before starting `py -m ezstimate.server`. BLS steel/aluminum updates do not require a key. Refreshes run at startup and daily while the local server is running, or whenever you press the refresh button. See [complete market feed and forecasting instructions](docs/MATERIAL_INTELLIGENCE.md).

**These persistent functions run only in the [local Python build](#quickstart). GitHub Pages remains a static browser demo without a private price database.** Full [data contract and roadmap](docs/MATERIAL_INTELLIGENCE.md).

## ERP-neutral purchase requests (new)

The local **05 Purchasing** section now drafts and records source-traceable material purchase requests, including job, material, quantity, purchasing unit, need date, requestor, and justification. Requests stay **draft** until the operator supplies a configured approval credential and an approver name. Approval freezes the document digest; with a configured transport it **automatically dispatches** the approved PR.

- **Outbox adapter:** exports approved requests as CSV or JSON for a purchasing team or ERP import service. `exported` does not mean it was accepted by an ERP.
- **HTTPS adapter:** sends a stable idempotency-keyed request to a configured HTTPS ERP/gateway endpoint. `endpoint_delivered` means a successful HTTP transport, **not** confirmation that the ERP created a native requisition.
- **Uncertain delivery:** retains the source and warns rather than silently retrying a request after timeout. Real ERP-specific acknowledgement, field mapping and full approval RBAC require their own adapters and auth configuration.

There is **no actual supplier purchase order issuance** in this build. No outbound sending happens by default without configuration. Setup, audit design, and integration contract: [ERP purchase requests](docs/ERP_PURCHASE_REQUESTS.md).

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

**Not yet:** OCR, fully automatic table recognition for arbitrary drawing formats, validated manufacturer pricing, connected historical ERP costs, native ERP-specific PR acceptance and supplier PO issuance, CAD mass estimation, or released quote authorization. All extracted fields need human review, especially tolerances and processes. Public fixtures and tests are synthetic; never commit customer drawings, prices, or POs.

## Verified engineering-suite wiring (2026-10-20)

The independently packaged estimating engine now has a tested local handoff to Axiom Beta: the real ForgeVault release service supplies checksum-verified PDF bytes and a specific version/package; EZstimate extracts revision/material candidates and computes explicit-cost draft pricing; the Axiom importer independently recomputes the quoted total and retains the exact source version, digest and itemized quote evidence. Axiom's Quoting screen displays the linked drawing and revision identifiers. The BEAN observation is recorded using EZstimate's actual optional BEAN Core journal interface.

[Cross-platform integration workflow](https://github.com/danieloculus0-bot/Axiom_Beta/actions/workflows/ezstimate-suite-wiring.yml) passed on Windows and Linux and [Axiom PR #16](https://github.com/danieloculus0-bot/Axiom_Beta/pull/16) merged. The Axiom importer is a local Python API, not an unauthenticated shop-network connector or an automatic quote approval. This implementation also shares the BEAN Gothic Lime design tokens (charcoal #0F1113 and lime #79DE4B) while keeping quote arithmetic separate from BEAN reasoning.
