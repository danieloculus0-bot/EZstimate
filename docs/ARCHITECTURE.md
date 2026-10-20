# EZstimate architecture and evidence contract

## System of record and responsibilities

- **ForgeVault/PDM** is the future controlled source for drawing revisions, file identities, immutable versions and document hashes. Alpha users upload copies manually; no live PDM API integration is claimed.
- **EZstimate** parses selectable PDF text, scans likely title-block regions and material-grade tokens, recognizes machine-readable PDF tables and CSV/XLSX BOM columns, reports candidates with source filenames/page or row, and builds costed *drafts*.
- **Axiom** owns released ERP estimate/job/PO entities and production actuals. EZstimate now stores **draft/approved purchase requests** in a local SQLite audit log; with an explicitly configured outbound adapter, approved PRs are exported to a file outbox or delivered to a configured HTTPS endpoint. This is not a supplier PO, native ERP acceptance, or unauthorized ERP database mutation.
- **BEAN Core** can receive actual observation events when installed in the same local environment and explicitly enabled via `EZSTIMATE_BEAN_DB`. This is implemented through `bean.integration.BeanReasoningLayer.record_event`, **not** a mock LLM answer. Observations retain source names, candidate field values and reference locations. The default review list remains clearly identified as EZstimate deterministic checks, not autonomous BEAN inference.

## Pricing formula and critical unknowns

Manufacturing cost = qty × [material unit cost × (1 + scrap%/100) + labor hours per unit × shop rate per hour + outside unit cost] + setup/lot.

Extended sales price = manufacturing cost / (1 - gross margin%/100). The engine uses decimal math and returns an incomplete quote when mandatory costs are absent, invalid, nonfinite or margin >= 100%. It does **not** substitute artificial prices or times. Zero inputs for outside, setup, scrap and margin are displayed and editable. Material and labor assumptions must be entered. Freight, taxes, and approval remain unknown/not approved.

## Coherent UI

Near black `#080d0c`, charcoal-green `#17211c`, acid lime `#c5ff4a`, mint `#5ff39a`, muted `#afc2b5`, strong borders `#2b443b`. Four stages: Import, Review, Cost, BEAN. Proposals are never described as approved. Official BEAN mascot is copied byte-for-byte locally from BEAN's `docs/bean-official.webp`.

## Limitations and engineering roadmap

- No OCR for scanned/image-only PDFs yet; structured table recognition is not guaranteed for arbitrary supplier drawings.
- No automated CAD nesting, weight/yield, bend count, cut length, weld inches, finish area, tolerance-time estimates or machine routing yet.
- The local SQLite pricebook now retains dated, source-referenced supplier quotes, POs and invoices by exact material key and unit. It does **not** import ERP purchasing history or validate supplier prices independently; automatic quantity-break recommendations and supplier lead-time confirmations remain future work.
- Local material-market pressure indicators now retain dated manually entered diesel, steel/aluminum, lead-time and sentiment data. Live automatic market feeds and historical price-forecast evaluation remain future work. No estimate-versus-actual feedback loop or live BEAN inference yet.
- Implement versioned cost books, accepted-source field overrides, full PO-line reconciliation, ForgeVault/Axiom adapters, and a real BEAN proposal/evidence loop with independently verified outcomes before production claims.

Public tests use synthetic values and artifacts. Keep company drawings, customer POs and actual shop rates outside this repository.

## Tested Axiom import

Axiom's local module at superforge/integrations/ezstimate_quote.py imports an explicit EZstimate draft quote proposal. The caller must supply the exact released ForgeVault file bytes and manifest; Axiom checks SHA-256 and independently recalculates numeric costs. It persists the source record, exact version UUID, release-package number and proposal digest. Conflicting use of a quote number is refused and successful re-import is idempotent. Only review_required quotes can enter this path; no public HTTP write endpoint or purchase order is created. CI independently checks the real ForgeVault/EZstimate/Axiom/BEAN handoff on both Windows and Linux. The release state originates at ForgeVault and is not cryptographically authenticated by merely possessing its JSON manifest.

## Price Memory and Material Forecast (implemented 2026-10-20)

See [MATERIAL_INTELLIGENCE.md](MATERIAL_INTELLIGENCE.md). The local Python app uses `ezstimate/pricing.py`, a SQLite database stored outside the repository by default, and `/api/pricing/*` routes. A user can explicitly choose a historical **per-each** unit cost for a quote line. There is no silent cost escalation from sentiment, fuel or commodity pressure. BEAN Core can receive actual evidence via `journal_market_review`; it currently stores observations, not tested future predictions. The old MID JobBOSS forecast fields now have an in-memory read-only XLSX preview adapter and browser UI. It recognizes material demand events, risk-register data and buyer action queues, retaining source sheet/row. It does not persist inventory projections, change ERP or infer a material price.

## ERP-neutral purchase requisitions

See [ERP_PURCHASE_REQUESTS.md](ERP_PURCHASE_REQUESTS.md). The canonical `axiom.purchase_request.v1` material/job request schema and approval SHA-256 separate request generation, human approval and dispatch. The `ERP_ADAPTER` transport contract currently supports offline JSON/CSV outbox and configured HTTPS JSON delivery, with stable request IDs and no automatic retry for uncertain network outcomes. Native ERP purchase-requisition response mapping/acceptance receipts and an authenticated enterprise RBAC approval directory are **not implemented**. The static Pages demo does not dispatch purchases.
