# ERP-neutral purchase request approval and delivery

EZstimate's local purchasing workbench can draft material requests and, **after a recorded human approval**, route them through a configured delivery adapter. A request is NOT a supplier PO, and a successful file/HTTP transport is NOT proof that the target ERP created a requisition.

## Flow

1. Material Forecast/MID flags missing inventory or a job's demand. Purchasing/estimating reviews actual material code, required quantity, purchasing unit, due date, and job.
2. User drafts a PR in section **05 Purchasing**. It persists in the same local SQLite database as pricing history. A unique request ID, document digest and append-only status events are recorded.
3. Someone holding the configured approval credential explicitly approves the immutable draft. The action records the claimed approver name and SHA-256 of the approved version; no provider-specific identity authentication or RBAC exists yet. This shared local credential is not a full enterprise approval system.
4. If an outbound adapter is configured, approval immediately triggers dispatch. Otherwise it remains `approved` and can be dispatched after configuring a connector. No unapproved request can be dispatched.
5. An approved PR is delivered to a **file outbox** (for subsequent ERP CSV/JSON import) or **HTTPS API endpoint** (via an integration gateway/adapter). Each delivery uses the same stable request ID and idempotency header.
6. The local audit trail distinguishes `draft`, `approved`, `dispatching`, `exported`, `endpoint_delivered`, and `delivery_unknown`. A timeout stops automatic retries pending reconciliation, so it won't silently create duplicate requisitions.
7. ERP-specific mappers later convert the canonical schema into the target ERP's native fields and read the ERP's actual purchase-requisition reference and status.

## Supported transports now

| Mode | What it does | What it does NOT establish |
| --- | --- | --- |
| `outbox` | Writes an idempotent local JSON or CSV export with material lines and approval details | Import into an ERP or a sent supplier PO |
| `https` | POSTs canonical `axiom.purchase_request.dispatch.v1` JSON to a fixed configured HTTPS receiver | That a named ERP accepted a native requisition |

Nothing is sent externally in the default unconfigured state. No native SAP/NetSuite/Dynamics/Epicor/JobBOSS adapter is claimed. An ERP-neutral contract is the starting point for those adapters, not a promise that one JSON payload natively works in every ERP.

### Windows: local outbox (no network deliveries)

```powershell
$env:EZSTIMATE_APPROVAL_TOKEN = Read-Host "Set the local PR approval credential"
$env:EZSTIMATE_ERP_MODE = "outbox"
$env:EZSTIMATE_ERP_OUTBOX_FORMAT = "csv"   # or "json"
$env:EZSTIMATE_ERP_OUTBOX = "$env:LOCALAPPDATA\EZstimate\erp_outbox"
py -m ezstimate.server
```

Section **05 Purchasing** creates a draft, requests the approval credential, and writes an export to the outbox after approval. The export must still be imported by the ERP or a configured import service. The supplier has not been ordered.

### HTTPS receiver / middleware / ERP adapter

```powershell
$env:EZSTIMATE_APPROVAL_TOKEN = Read-Host "Set the local PR approval credential"
$env:EZSTIMATE_ERP_MODE = "https"
$env:EZSTIMATE_ERP_ENDPOINT = "https://your-company-gateway.example/api/purchase-requests"
$env:EZSTIMATE_ERP_BEARER_TOKEN = Read-Host "ERP gateway bearer token"
py -m ezstimate.server
```

The URL is an administrator-configured fixed HTTPS endpoint, never derived from uploaded documents or browser request data. Redirects are not followed; server-side bearer credentials aren't embedded in exported PR data. The request includes `Idempotency-Key: PR-...`, the approved payload digest and source lines. Only HTTP 200/201/202 is counted as **endpoint delivery**, not ERP creation. The receiving connector must implement the target ERP's auth, field mapping, state/status receipt, duplication checks and error reconciliation.

An enterprise production deployment should replace the shared approval secret with authenticated users, delegated approval roles and a native outbox/message dispatcher. This alpha is bound to localhost and not intended to be exposed unauthenticated on the shop network.

## Canonical purchase-request fields

Top-level: `schema`, `requested_by`, `department`, `justification`, `source_system`, `lines`.

Per line: `material_key`, `description`, `quantity`, `unit`, `needed_by`, `job`, `supplier_preference`, `source_ref`.

Approval/transport envelope: `request_id`, `approval.approved_by`, `approval.approved_utc`, `approval.approval_sha256`, `payload_sha256`, `payload`.

Material codes, unit conversions and purchasing quantity must be reviewed for the *actual ERP's* material master. A part in a manufacturing estimate is not automatically a stock item.

## Test coverage

Windows and Linux synthetic tests assert: persistence, client idempotency, no dispatch before approval, missing/invalid approval credential, immutable content digest, JSON/CSV export, spreadsheet formula escaping, strict HTTPS transport configuration, idempotency headers, ambiguous network failures and REST endpoints.

No real purchasing credentials, proprietary ERP datasets, customer POs or supplier orders are in public test fixtures.
