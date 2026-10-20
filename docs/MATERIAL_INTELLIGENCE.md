# Material Forecast and price memory integration (alpha)

This is the next module inside EZstimate, not a second disconnected estimate calculator.

## What's implemented

- `ezstimate/pricing.py` persists real, dated purchasing price observations to **local SQLite** by exact ERP material key, original quote/PO/invoice reference, supplier, source quantity, date, currency and price unit.
- Source records are explicitly entered or imported by a trusted local operator. Missing cost remains missing. A supplier price, an estimated material allowance and a commodity indicator are distinct kinds of evidence.
- The local workbench has Price Memory and Material Market Watch panels.
- A retrieved cost does **not** modify an estimate. The operator can explicitly apply an **ea** price to a quote line, with the source retained. Sheet, lb and ft cannot be used as per-part costs without calculating a verified conversion/yield.
- Five input series are available for manual observation: diesel USD/gal, steel market index, aluminum market index, supplier lead time in days and sentiment score 0-100.
- The pressure-watch logic compares dated values. Significant upward movement results in transparent points and an **elevated/high** watch. Missing history produces **insufficient**, not an invented zero or a confident prediction. Readings over 90 days old do not contribute pressure points.
- With a real optional BEAN Core connection, the market assessment can be journaled as a source-backed observation. This invokes BEAN's actual persistence interface. It is **not** proof of model inference, self-learning, validated spike prediction, or automatic price approval.
- Windows/Linux tests exercise history persistence, source collisions, material/unit matching, market-risk labels, Flask integration and missing-BEAN behavior.

## Run locally

```powershell
git clone https://github.com/danieloculus0-bot/EZstimate.git
cd EZstimate
py -m pip install -e .
py -m ezstimate.server
```

Open http://127.0.0.1:8765 and use **04 Price Memory**. The SQLite database lives by default at `~/.ezstimate/price_memory.sqlite3`, or set `EZSTIMATE_PRICE_DB` to a different local file path. Keep this database under your own access permissions and backup plan; **never check it or real supplier prices into the public repository**.

Example API call to store a *fictional* dated invoice price (PowerShell):

```powershell
$body = @{
  material_key="SHT-STL-0250X60X120-A36-HR";supplier="Example Metals";
  source_type="invoice";source_ref="INV-DEMO-001";effective_date="2026-01-15";
  unit_price="220.25";price_unit="sheet";quantity="12";currency="USD"
} | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8765/api/pricing/prices -Method POST -ContentType application/json -Body $body
```

`GET /api/pricing/prices?material_key=...&price_unit=sheet` returns source-identified history and the newest candidate for human review. `GET /api/pricing/pressure?family=steel` reports the signal history and transparent watch points.

## Reuse of the earlier Material Intelligence Dashboard (MID)

MID already contained the correct operational entities: normalized material keys, shortage quantity and value, forecast need windows, job due dates, supplier lead times, PO commitments and market pressure. EZstimate should reuse this **data contract** rather than trying to treat every spreadsheet field as a historical purchasing price.

| MID field family | EZstimate responsibility | Avoid |
| --- | --- | --- |
| Material part / normalized key / grade / shape | Exact lookup key and supported normalized catalog metadata | Treating A36 alone as a unique purchasable item |
| Job, customer, part, due date / need window | Quote demand and timing, linked to Axiom | Confusing an assembly BOM with purchased stock |
| On hand / on order / needed / adjusted balance | Purchasing exposure signal | Assuming a positive forecast balance is a guaranteed available allocation |
| Unit cost, supplier, PO or invoice | Historical price only when dated, sourced, with known unit and actual supplier evidence | Treating an unknown import cost as an invoice |
| Lead time, promised receipt and market indicators | Material supply/price-pressure watch, with dated evidence | Inflating a quote automatically |
| Forecast action / owner / review date | Review work queue | Equating a heuristic with a supplier-confirmed commitment |

The first versioned MID **XLSX read-only adapter** is now available at \`/api/pricing/mid-preview\` with a companion file picker in the local interface. It recognizes JobBOSS demand events, risk-register rows, and buyer action queues while retaining sheet/row source evidence. It does not automatically import MID forecast records into the persistent pricing database or change Axiom's released estimate. Expanded column/unit verification and sustained forecast snapshots are still planned.

## BEAN learning loop (next increment)

1. Retain a dated material/supplier baseline purchase price and proposed risk hypothesis.
2. When a later purchase price arrives, compare **matching material code, unit, quantity break and supplier** against the baseline.
3. Track separate errors by material family and signal combination with controls for market regime and date. Publish both hits and misses to BEAN Core.
4. Promote a forecasting rule only when its improvement over a simple historical baseline is demonstrated on holdout periods.
5. Let BEAN propose a reserve or re-quote warning, but leave the estimator's entered cost and final quote authorization unchanged unless the operator elects a change.

## Live data integration (not yet implemented)

A future approved adapter can retrieve public diesel and commodity producer-price series from documented, licensed sources (such as EIA and BLS/FRED), recording provider, series ID, publication date, unit, timestamp and cache freshness. Sources are not one-to-one predictors of fabrication stock costs. Sector news and sentiment need a documented scoring method plus attribution before they are promoted into a quantitative feature. Supplier lead times and local surcharges still require purchasing data.

**GitHub Pages** serves the stand-alone, browser-side estimate demo. It has no local SQLite or BEAN Core process. The persistent Price Memory workbench runs in the **Python local build** only.
