# EZstimate: Axiom Reconciled Actual-Cost Intake

EZstimate can receive actual source-backed invoice cost observations from Axiom while preserving the fundamental boundary: **quoted, PO-agreed, invoiced and fully landed costs are distinct**. No invoice or freight number is silently copied into an estimate.

## Operator workflow

1. In local Axiom, finish the purchase order, receipt and supplier invoice review at `/purchasing/costs`. Correct any HOLD or unresolved variance.
2. Open `/purchasing/costs/feedback.json` in the local Axiom workbench and save the JSON. Every entry is a **reconciled** invoice line with an explicit material code, stocking unit, original agreed PO price, invoice material unit price, freight-inclusive landed unit price, supplier, source and invoice date. No PO invoice payment is implied.
3. On the EZstimate machine, run `python -m ezstimate.axiom_cost_feedback stage <saved-feedback.json>` or supply `--db <path>` before the subcommand to target a test price-memory database.
4. Run `python -m ezstimate.axiom_cost_feedback inbox` to review the pending observation keys.
5. For each verified supplier invoice line you accept, run `python -m ezstimate.axiom_cost_feedback adopt AXIOM-INVOICE-LINE-123 --reviewer "Local purchasing reviewer"`.

This uses the existing EZstimate `purchase_prices` memory with source type `invoice` and immutable observation source key. The adopted unit price is the **supplier invoice material unit price**. Freight/tax/other landed costs stay in the source notes, never disguised as the raw material unit price. Existing estimates are not automatically recalculated.

## Integrity and limits

- Staging is atomic; malformed or conflicting lines prevent partial import.
- Re-importing identical source observations is idempotent; the same invoice-line reference with changed figures is rejected.
- Staging does not modify price memory, and adoption requires an explicit local review action. Pending prices are not quote candidates.
- The source is a local export of reconciled Axiom invoice evidence. This does not authenticate the user, reverify PDF bytes, or establish physical material lot traceability.
- Missing stock unit conversions, multiple Axiom installations sharing invoice IDs, ERP/provider acknowledgements and automatic supplier/AP integration remain future integration tasks.
- Use appropriate source management and keep the workbenches local until authenticated identity and permissions are implemented.
