# EZstimate architecture and evidence contract

## System of record and responsibilities

- **ForgeVault/PDM** is the future controlled source for drawing revisions, file identities, immutable versions and document hashes. Alpha users upload copies manually; no live PDM API integration is claimed.
- **EZstimate** parses selectable PDF text, scans likely title-block regions and material-grade tokens, recognizes machine-readable PDF tables and CSV/XLSX BOM columns, reports candidates with source filenames/page or row, and builds costed *drafts*.
- **Axiom** will own released ERP estimate/job/PO entities and production actuals. EZstimate does not create orders or alter ERP data.
- **BEAN Core** can receive actual observation events when installed in the same local environment and explicitly enabled via `EZSTIMATE_BEAN_DB`. This is implemented through `bean.integration.BeanReasoningLayer.record_event`, **not** a mock LLM answer. Observations retain source names, candidate field values and reference locations. The default review list remains clearly identified as EZstimate deterministic checks, not autonomous BEAN inference.

## Pricing formula and critical unknowns

Manufacturing cost = qty × [material unit cost × (1 + scrap%/100) + labor hours per unit × shop rate per hour + outside unit cost] + setup/lot.

Extended sales price = manufacturing cost / (1 - gross margin%/100). The engine uses decimal math and returns an incomplete quote when mandatory costs are absent, invalid, nonfinite or margin >= 100%. It does **not** substitute artificial prices or times. Zero inputs for outside, setup, scrap and margin are displayed and editable. Material and labor assumptions must be entered. Freight, taxes, and approval remain unknown/not approved.

## Coherent UI

Near black `#080d0c`, charcoal-green `#17211c`, acid lime `#c5ff4a`, mint `#5ff39a`, muted `#afc2b5`, strong borders `#2b443b`. Four stages: Import, Review, Cost, BEAN. Proposals are never described as approved. Official BEAN mascot is copied locally from BEAN's `docs/bean-icon.svg`.

## Limitations and engineering roadmap

- No OCR for scanned/image-only PDFs yet; structured table recognition is not guaranteed for arbitrary supplier drawings.
- No automated CAD nesting, weight/yield, bend count, cut length, weld inches, finish area, tolerance-time estimates or machine routing yet.
- No dated cost books, quantity breaks, supplier quotes, material certifications, lead-time confirmation or independent price verification yet.
- No historical estimate versus actual feedback loop or live BEAN inference yet.
- Implement versioned cost books, accepted-source field overrides, full PO-line reconciliation, ForgeVault/Axiom adapters, and a real BEAN proposal/evidence loop with independently verified outcomes before production claims.

Public tests use synthetic values and artifacts. Keep company drawings, customer POs and actual shop rates outside this repository.

## Tested Axiom import

Axiom's local module at superforge/integrations/ezstimate_quote.py imports an explicit EZstimate draft quote proposal. The caller must supply the exact released ForgeVault file bytes and manifest; Axiom checks SHA-256 and independently recalculates numeric costs. It persists the source record, exact version UUID, release-package number and proposal digest. Conflicting use of a quote number is refused and successful re-import is idempotent. Only review_required quotes can enter this path; no public HTTP write endpoint or purchase order is created. CI independently checks the real ForgeVault/EZstimate/Axiom/BEAN handoff on both Windows and Linux. The release state originates at ForgeVault and is not cryptographically authenticated by merely possessing its JSON manifest.
