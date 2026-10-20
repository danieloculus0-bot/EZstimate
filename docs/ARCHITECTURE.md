# EZstimate engineering-suite boundaries

ForgeVault owns the authoritative drawing release, file version and exact SHA-256 PDF bytes. EZstimate interprets actual PDF bytes and flags material/drawing/PO candidates for review; a printed "released" label is not ForgeVault authorization.

EZstimate's pricing derives exclusively from explicit numeric inputs, not guessed machining times or steel prices. The proposed quote has status review_required. It does not authorize purchasing, PO acceptance or product release.

Axiom owns ERP quotation intake and related customer/part records. The independently packaged importer accepts the EZstimate quote_proposal.v1 and stores a reviewed draft, not an approved estimate. No unauthenticated remote write endpoint is added.

An optional real BEAN Core CommandInbox log_note receives unverified quote information when EZSTIMATE_BEAN_INBOX is configured. An inbox receipt is a transport event, not an AI approval or intelligence claim.

Run the UI only at 127.0.0.1:8765; do not expose it to a shared network without authentication. Never commit customer drawings or private pricing to public repositories.
