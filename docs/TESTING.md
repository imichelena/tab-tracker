# Live Test Plan — Tab Tracker POS Extension

**Last updated:** 2026-07-19
**Branch:** `feat/pos-extension` (HEAD 9fd346e)
**Author:** Build agent (fills gap left by QA's BLOCKED SPEC §8.2 tests — QA did static review only, 9/10 tests unresolved)

> ⚠️ **Why this doc exists:** QA's SPEC §8.2 test cases (T01–T10) were all marked **BLOCKED** because no live PostgreSQL database was available in the audit environment. This doc provides the actionable test plan to verify the entire stack on a real VPS with a dev store. See `docs/QA_REPORT.md §3.1` for the blocked test matrix.

---

## Prerequisites

| Item | Required | Notes |
|------|----------|-------|
| **DEV database** | PostgreSQL instance on the opencpo-demo VPS (178.104.146.136 / Tailscale 100.122.187.17) with `tabtracker` DB and `tab_tracker` schema. | Use existing prod DB as base; migration is additive — no destructive changes. See `docs/DEPLOYMENT.md §3`. |
| **API key** | `TAB_TRACKER_API_KEY` value set in environment. For pilot: `pos-extension-pilot-key-2026`. | Must match what the extension sends. |
| **Extension built locally** | `cd extension && npm install && npm run build` succeeds (exit 0). | Verify before deploying. |
| **Shopify CLI v3** | Installed and authenticated against `amsterdam-baking-company.myshopify.com`. | `shopify version` → 3.x, `shopify whoami` → authenticated. |
| **Dev store access** | `amsterdam-baking-company.myshopify.com` — custom Shopify app, POS device assigned. | Not App Store; internal custom app. |

---

## Phase 1: Backend Smoke Tests

Apply the migration to the DEV database, start the backend on an alternative port to avoid conflict with production (which runs on `:8095`), and curl each `/api/v1/*` endpoint.

### 1a. Apply Migration to DEV

```bash
# DEV DB — using the prod DB as base (migration is additive)
psql -U tabtracker -d tabtracker -h 127.0.0.1 \
  -f /opt/tab-tracker/migrations/002_pos_extension.sql

# Verify tables exist
psql -U tabtracker -d tabtracker -h 127.0.0.1 \
  -c "\dt tab_tracker.pos_sessions"

# Verify columns exist
psql -U tabtracker -d tabtracker -h 127.0.0.1 \
  -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='tab_tracker' AND table_name='tabs' AND column_name IN ('pos_cart_sent_at','pos_terminal_id');"
```

**Expected:** All statements succeed. `pos_sessions` table created. `tabs` gains 2 new columns. `transactions` gains 3 new columns.

### 1b. Start Backend on Alt Port :18095

Production `tab-tracker` (gunicorn) is already bound to `:8095`. Use port **18095** for DEV.

```bash
cd /opt/tab-tracker
export TAB_TRACKER_API_KEY=pos-extension-pilot-key-2026
export TAB_TRACKER_PORT=18095
export POS_EXTENSION_ORIGIN=*
export CHECKOUT_METHOD=pos_extension
export SHOPIFY_MOCK=true

# Start with uvicorn directly (no systemd, no nginx)
uvicorn app:app --host 0.0.0.0 --port 18095
```

**Verify startup:**
```bash
curl http://127.0.0.1:18095/health
# Expected: {"status":"ok","service":"tab-tracker","shopify_mock":true}
```

### 1c. Smoke-Test All 12 Endpoints

```bash
API_KEY=pos-extension-pilot-key-2026
BASE=http://127.0.0.1:18095
```

| # | Endpoint | Method | Expected | Command |
|---|----------|--------|----------|---------|
| 1 | `/api/v1/products` | GET | 200, JSON array with `id`, `name`, `price`, `category_id`, `category_name`, `shopify_variant_id`, `override_price` | `curl -s -H "X-API-Key: $API_KEY" $BASE/api/v1/products \| jq '. \| length'` |
| 2 | `/api/v1/categories` | GET | 200, JSON array sorted by `sort_order` | `curl -s -H "X-API-Key: $API_KEY" $BASE/api/v1/categories \| jq '.[].name'` |
| 3 | `/api/v1/tables` | GET | 200, JSON array of tables | `curl -s -H "X-API-Key: $API_KEY" $BASE/api/v1/tables \| jq '.[].name'` |
| 4 | `/api/v1/tabs/open` | GET | 200, JSON array of open tabs (may be empty) | `curl -s -H "X-API-Key: $API_KEY" $BASE/api/v1/tabs/open \| jq '. \| length'` |
| 5 | `/api/v1/tabs` | GET | 200, JSON array (all tabs, may be empty) | `curl -s -H "X-API-Key: $API_KEY" $BASE/api/v1/tabs \| jq '. \| length'` |
| 6 | `POST /api/v1/tabs` | POST | 201, tab object with `id` | `curl -s -X POST -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" -d '{"table_id":1,"pos_terminal_id":"dev-test-001"}' $BASE/api/v1/tabs \| jq '.id'` |
| 7 | `POST /api/v1/tabs/{id}/items` | POST | 200, updated items array | `curl -s -X POST -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" -d '{"product_id":1}' $BASE/api/v1/tabs/{TAB_ID}/items \| jq '.items \| length'` |
| 8 | `DELETE /api/v1/tabs/{id}/items/{item_id}` | DELETE | 200, updated items array | `curl -s -X DELETE -H "X-API-Key: $API_KEY" $BASE/api/v1/tabs/{TAB_ID}/items/{ITEM_ID} \| jq '.items \| length'` |
| 9 | `PATCH /api/v1/tabs/{id}/items/{item_id}` | PATCH | 200, updated item | `curl -s -X PATCH -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" -d '{"quantity":3}' $BASE/api/v1/tabs/{TAB_ID}/items/{ITEM_ID}` |
| 10 | `POST /api/v1/tabs/{id}/close` | POST | 200, tab closed | `curl -s -X POST -H "X-API-Key: $API_KEY" $BASE/api/v1/tabs/{TAB_ID}/close \| jq '.status'` |
| 11 | `POST /api/v1/tabs/{id}/send-to-cart` | POST | 200, `transaction_id` | `curl -s -X POST -H "X-API-Key: $API_KEY" $BASE/api/v1/tabs/{TAB_ID}/send-to-cart \| jq '.transaction_id'` |
| 12 | `GET /api/v1/transactions/{tx_id}` | GET | 200, transaction object | `curl -s -H "X-API-Key: $API_KEY" $BASE/api/v1/transactions/{TX_ID} \| jq '.checkout_method'` |

**Auth negative tests (all should return 401):**

```bash
# Missing API key
curl -s $BASE/api/v1/products | jq '.detail'
# Expected: "Invalid or missing API key"

# Wrong API key
curl -s -H "X-API-Key: wrong-key" $BASE/api/v1/products | jq '.detail'
# Expected: "Invalid or missing API key"
```

---

## Phase 2: Backend Integration Tests

These tests require a live DB with real data. They verify the full backend flow end-to-end.

### Test 2a: Open Tab → Add Item (Override Price) → Send-to-Cart → Verify Transaction → Close Tab

```bash
# 1. Open a tab
TAB=$(curl -s -X POST -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"table_id":1,"pos_terminal_id":"dev-test-001"}' \
  $BASE/api/v1/tabs | jq -r '.id')
echo "Tab: $TAB"

# 2. Add an item that has an active price override
#    (check which products have override_price != null first)
PRODUCT=$(curl -s -H "X-API-Key: $API_KEY" $BASE/api/v1/products \
  | jq '.[] | select(.override_price != null) | .id' | head -1)
echo "Product with override: $PRODUCT"

curl -s -X POST -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"product_id\":$PRODUCT}" \
  $BASE/api/v1/tabs/$TAB/items | jq '.total'

# 3. Send to cart
SEND_RESULT=$(curl -s -X POST -H "X-API-Key: $API_KEY" \
  $BASE/api/v1/tabs/$TAB/send-to-cart)
echo "$SEND_RESULT" | jq '.'
TX_ID=$(echo "$SEND_RESULT" | jq -r '.transaction_id')
echo "Transaction: $TX_ID"

# 4. Verify transaction exists in DB directly
psql -U tabtracker -d tabtracker -h 127.0.0.1 \
  -c "SELECT id, tab_id, total, checkout_method, pos_terminal_id, created_at FROM tab_tracker.transactions WHERE id=$TX_ID;"

# 5. Verify tab status is "sent"
curl -s -H "X-API-Key: $API_KEY" $BASE/api/v1/tabs/$TAB | jq '.status'
# Expected: "sent"

# 6. Close the tab
curl -s -X POST -H "X-API-Key: $API_KEY" \
  $BASE/api/v1/tabs/$TAB/close | jq '.status'
# Expected: "closed"
```

### Test 2b: Double-Send Rejection

```bash
# Open a new tab, add item, send it
TAB2=$(curl -s -X POST -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"table_id":1,"pos_terminal_id":"dev-test-001"}' \
  $BASE/api/v1/tabs | jq -r '.id')
curl -s -X POST -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"product_id":1}' $BASE/api/v1/tabs/$TAB2/items
curl -s -X POST -H "X-API-Key: $API_KEY" \
  $BASE/api/v1/tabs/$TAB2/send-to-cart | jq '.status'
# Expected: "sent"

# Try to send again — must reject
curl -s -X POST -H "X-API-Key: $API_KEY" \
  $BASE/api/v1/tabs/$TAB2/send-to-cart | jq '.detail'
# Expected: "Tab already sent"
```

### Test 2c: Empty Tab Rejection

```bash
# Open a tab but DON'T add items
TAB3=$(curl -s -X POST -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"table_id":1,"pos_terminal_id":"dev-test-001"}' \
  $BASE/api/v1/tabs | jq -r '.id')

# Try to send empty tab
curl -s -X POST -H "X-API-Key: $API_KEY" \
  $BASE/api/v1/tabs/$TAB3/send-to-cart | jq '.detail'
# Expected: "Cannot send empty tab"
```

### Test 2d: Auth 401 Cases

```bash
# No API key on write endpoint
curl -s -X POST $BASE/api/v1/tabs \
  -H "Content-Type: application/json" \
  -d '{"table_id":1}' | jq '.detail'
# Expected: "Invalid or missing API key"

# No API key on send-to-cart
curl -s -X POST $BASE/api/v1/tabs/1/send-to-cart | jq '.detail'
# Expected: "Invalid or missing API key"

# Wrong API key on close
curl -s -X POST -H "X-API-Key: wrong-key" \
  $BASE/api/v1/tabs/1/close | jq '.detail'
# Expected: "Invalid or missing API key"
```

---

## Phase 3: Extension Build + Dev Server

```bash
cd /home/nano/tab-tracker-repo/extension

# Install deps (if not already)
npm install

# Build for production (verify clean)
npm run build
# Expected: exit 0, produces dist/index.js, dist/Modal.js, dist/jsx-runtime-D4IR1xdk.js

# Start dev server (Shopify CLI v3)
npm run dev
# This launches Shopify CLI tunnel + rebuild watcher.
# The CLI will print a URL like:
#   https://<random>.ngrok.io or "Extension URL: ..."
# Wait for "Application startup complete" before proceeding.
```

**Verify:** Open the URL in browser — you should see the extension sandbox (Shopify POS preview).

---

## Phase 4: Dev Store Deploy

### 4a. Configure `shopify.extension.toml` [settings]

Edit `extension/shopify.extension.toml` and add/review the `[settings]` section:

```toml
[settings]
# Backend URL the extension will call — use the VPS Tailscale IP for DEV
# ⚠️ DO NOT use port 18095 in POS devices (POS uses HTTPS via extension)
# For DEV behind Tailscale, point to the VPS
backend_url = "https://178.104.146.136:18095"
# Or if behind Tailscale:
# backend_url = "http://100.122.187.17:18095"

# API key must match TAB_TRACKER_API_KEY on the backend
api_key = "pos-extension-pilot-key-2026"

# Default terminal ID for this POS device
default_terminal_id = "pos-dev-1"
```

> **Important:** In production, `backend_url` must be the public HTTPS endpoint (Caddy reverse proxy), not the Tailscale IP. `api_key` must be injected via Shopify app metafields or build-time substitution — never hardcoded (see SEC-001).

### 4b. Install on Dev Store

```bash
# Navigate to extension directory
cd /home/nano/tab-tracker-repo/extension

# Deploy to dev store via Shopify CLI
shopify app deploy --store amsterdam-baking-company.myshopify.com
# Or for explicit version:
shopify extension register --store amsterdam-baking-company.myshopify.com

# The extension should now appear under:
#   Shopify Admin → Apps → <your custom app> → Extensions → POS UI Extension
```

### 4c. Load POS Device

1. Open the Shopify POS app on the assigned dev device.
2. Navigate to the **Home** screen.
3. The Tab Tracker tile should appear (based on `pos.home.tile.render` target).
4. Tap the tile — the full Tab Tracker modal should open.

**If the tile doesn't appear:**
- Verify the extension is assigned to the POS device in Shopify Admin.
- Check `shopify.extension.toml` `[extensions]` has `type = "pos_ui_extension"` and correct targets.
- Re-run `shopify extension register` or re-deploy.

---

## Phase 5: End-to-End Flow on POS

This is the golden path — the core feature of the entire project.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Open Tab Tracker from POS home tile (the `pos.home.tile.render` tile) | Modal opens showing product grid + empty tab bill |
| 2 | Select a category from the pill bar | Products filtered by category |
| 3 | Tap a product to add it to the tab | Item appears in bill panel with name, qty=1, price |
| 4 | Tap a product that has a Shopify variant ID | Item added with correct `shopify_variant_id` |
| 5 | Tap a product with price override | Item added with override price (for POS Cart API fallback, this will use `addCustomSale`) |
| 6 | Increment item quantity in bill | Total updates correctly |
| 7 | Decrement item quantity in bill | Total updates; qty reaches 0 → item removed |
| 8 | Remove item from bill | Item removed; total recalculated |
| 9 | **Send to POS Cart** | Items pushed to POS cart via Cart API (`clearCart` → `addLineItem`/`addCustomSale`). Backend `POST /api/v1/tabs/{id}/send-to-cart` records transaction. Check Shopify POS cart: items visible with correct names and prices. |
| 10 | Return to Tab Tracker | Tab shows "sent" status. Send button disabled. |
| 11 | Navigate to Shopify POS checkout | Cart contains all items from the tab. Proceed to payment. |
| 12 | Complete payment in Shopify POS checkout | Payment processed natively by Shopify. |
| 13 | Return to Tab Tracker, close tab | Tab status = "closed". |
| 14 | **Verify in backend DB** | `psql -c "SELECT * FROM tab_tracker.transactions ORDER BY id DESC LIMIT 1;"` — verify `tab_id`, `total`, `checkout_method='pos_extension'`, `pos_terminal_id`, `pos_order_id` (if Cart API returns one) are correct. |

---

## Phase 6: Edge Cases

### Test 6a: Empty Tab → Expect Reject

From the POS extension:
1. Open Tab Tracker without adding any items.
2. Tap "Send to POS Cart" (or attempt send).
3. **Expected:** The send is rejected — either extension-side (button disabled when tab empty) or backend returns 400 "Cannot send empty tab".

### Test 6b: Tab with 20+ Items

1. Open Tab Tracker.
2. Add 20+ products to the tab (repeat add-product steps).
3. Scroll the bill panel — verify all items render and scroll smoothly.
4. Send to cart — verify all items reach the POS cart.
5. **Expected:** No performance degradation. All items transferred correctly.

### Test 6c: Rapid Tab Switches

1. Open Tab A, add 2 items.
2. Switch to Tab B (or open a new tab for another table).
3. Go back to Tab A.
4. **Expected:** Tab A's items are preserved. No data loss on tab switch.

### Test 6d: Backend Timeout Simulation

1. While the extension is running, stop the backend (`Ctrl+C` on uvicorn).
2. Try to open a tab or add an item from the extension.
3. **Expected:** Error banner appears with retry button. Extension does not crash.
4. Restart the backend.
5. Tap retry.
6. **Expected:** Normal operation resumes.

---

## Test Case Checklist

Fill in the Pass/Fail/Blocked column during testing.

### Backend Smoke Tests (Phase 1)

| TC ID | Test Case | Expected | Result (Pass/Fail/Blocked) | Notes |
|-------|-----------|----------|---------------------------|-------|
| SM-01 | Migration applied to DEV DB | All tables/columns created | | |
| SM-02 | Backend starts on :18095 | /health returns 200 | | |
| SM-03 | GET /api/v1/products | 200, JSON array | | |
| SM-04 | GET /api/v1/categories | 200, sorted by sort_order | | |
| SM-05 | GET /api/v1/tables | 200, JSON array | | |
| SM-06 | GET /api/v1/tabs/open | 200, JSON array | | |
| SM-07 | GET /api/v1/tabs | 200, JSON array | | |
| SM-08 | POST /api/v1/tabs | 201, tab with id | | |
| SM-09 | POST /api/v1/tabs/{id}/items | 200, items array | | |
| SM-10 | DELETE /api/v1/tabs/{id}/items/{item_id} | 200, updated items | | |
| SM-11 | PATCH /api/v1/tabs/{id}/items/{item_id} | 200, updated item | | |
| SM-12 | POST /api/v1/tabs/{id}/close | 200, closed status | | |
| SM-13 | POST /api/v1/tabs/{id}/send-to-cart | 200, transaction_id | | |
| SM-14 | GET /api/v1/transactions/{tx_id} | 200, transaction object | | |
| SM-15 | Auth: missing API key | 401 | | |
| SM-16 | Auth: wrong API key | 401 | | |

### Backend Integration Tests (Phase 2)

| TC ID | Test Case | Expected | Result (Pass/Fail/Blocked) | Notes |
|-------|-----------|----------|---------------------------|-------|
| INT-01 | Open tab → add override_price item → send-to-cart → verify transaction DB row | Transaction row exists with correct `checkout_method='pos_extension'` | | |
| INT-02 | Open tab → add normal item → send-to-cart → close tab | Tab status transitions: open→sent→closed | | |
| INT-03 | Double-send rejected | 400 "Tab already sent" | | |
| INT-04 | Empty tab send rejected | 400 "Cannot send empty tab" | | |
| INT-05 | Close without send | Tab close succeeds | | |
| INT-06 | Close already-closed tab | Rejected (guard) | | |
| INT-07 | Add item with override_price → verify total uses override | Total includes override price, not base price | | |

### Extension Build + Dev Server (Phase 3)

| TC ID | Test Case | Expected | Result (Pass/Fail/Blocked) | Notes |
|-------|-----------|----------|---------------------------|-------|
| EXT-01 | npm install | exit 0, 0 vulnerabilities | | |
| EXT-02 | npm run build (production) | exit 0, dist/*.js produced | | |
| EXT-03 | npm run dev | CLI starts, tunnel URL printed | | |

### Dev Store Deploy (Phase 4)

| TC ID | Test Case | Expected | Result (Pass/Fail/Blocked) | Notes |
|-------|-----------|----------|---------------------------|-------|
| DEP-01 | shopify.extension.toml configured with backend_url/api_key/terminal_id | Settings present | | |
| DEP-02 | Extension deployed to dev store | Appears in Shopify Admin → Extensions | | |
| DEP-03 | POS device loads extension tile | Tile visible on POS home | | |
| DEP-04 | Tile opens modal | Modal renders with product grid | | |

### End-to-End POS Flow (Phase 5)

| TC ID | Test Case | Expected | Result (Pass/Fail/Blocked) | Notes |
|-------|-----------|----------|---------------------------|-------|
| E2E-01 | Open tab from POS tile | Modal shows empty tab bill | | |
| E2E-02 | Add product with shopify_variant_id | Item appears with correct price | | |
| E2E-03 | Add product with override_price | Item uses override price | | |
| E2E-04 | Increment qty → total updates | Total reflects new qty | | |
| E2E-05 | Decrement qty → item removed at 0 | Item disappears from bill | | |
| E2E-06 | Remove item | Item gone, total recalculated | | |
| E2E-07 | Send to POS Cart | Items in Shopify POS cart; backend transaction recorded | | |
| E2E-08 | Check POS cart items | Correct names, prices, quantities | | |
| E2E-09 | Complete payment in POS checkout | Payment processes | | |
| E2E-10 | Close tab after checkout | Tab status = closed | | |
| E2E-11 | Verify transaction in backend DB | `checkout_method='pos_extension'`, correct `tab_id`, `total` | | |
| E2E-12 | Tab shows "sent" status on return | Send button disabled | | |

### Edge Cases (Phase 6)

| TC ID | Test Case | Expected | Result (Pass/Fail/Blocked) | Notes |
|-------|-----------|----------|---------------------------|-------|
| EDGE-01 | Empty tab — attempt send | Blocked (UI or 400) | | |
| EDGE-02 | Tab with 20+ items — scroll + send | All items render, all transfer | | |
| EDGE-03 | Rapid tab switches — items preserved | No data loss | | |
| EDGE-04 | Backend timeout — error banner | Banner + retry; no crash | | |
| EDGE-05 | Backend restart — retry works | Normal ops resume | | |

---

## Rollback Steps (If Testing Fails)

### If Phase 1 (Backend smoke tests) fail:

```bash
# Stop the DEV backend
# (Ctrl+C on uvicorn process)

# Rollback migration (additive — drop new columns and table)
psql -U tabtracker -d tabtracker -h 127.0.0.1 <<'SQL'
BEGIN;
DROP TABLE IF EXISTS tab_tracker.pos_sessions CASCADE;
ALTER TABLE tab_tracker.tabs DROP COLUMN IF EXISTS pos_cart_sent_at;
ALTER TABLE tab_tracker.tabs DROP COLUMN IF EXISTS pos_terminal_id;
ALTER TABLE tab_tracker.transactions DROP COLUMN IF EXISTS pos_order_id;
ALTER TABLE tab_tracker.transactions DROP COLUMN IF EXISTS pos_terminal_id;
ALTER TABLE tab_tracker.transactions DROP COLUMN IF EXISTS checkout_method;
COMMIT;
SQL

# Verify rollback
psql -U tabtracker -d tabtracker -h 127.0.0.1 \
  -c "\dt tab_tracker.pos_sessions"  # Should show "Did not find any relation"

# Restart prod backend (on :8095) to confirm no regression
sudo systemctl restart tab-tracker
curl http://127.0.0.1:8095/health
```

> **Note:** The migration is additive — no existing data is modified. The rollback above is only needed if you want to fully undo. Leaving the new columns in place is harmless to the web UI (they're ignored by legacy queries).

### If Phase 3-5 (Extension) fail:

```bash
# Stop the extension dev server (Ctrl+C)

# Remove extension from dev store via Shopify CLI
shopify extension delete \
  --store amsterdam-baking-company.myshopify.com

# Clean local build artifacts
cd extension && rm -rf dist/ node_modules/

# Reset config
git checkout extension/shopify.extension.toml
```

### If Phase 2 integration tests fail (data corruption):

```bash
# Clean up test tabs from DB
psql -U tabtracker -d tabtracker -h 127.0.0.1 \
  -c "DELETE FROM tab_tracker.tab_items WHERE tab_id IN (SELECT id FROM tab_tracker.tabs WHERE status = 'sent');"
psql -U tabtracker -d tabtracker -h 127.0.0.1 \
  -c "DELETE FROM tab_tracker.transaction_items WHERE transaction_id IN (SELECT id FROM tab_tracker.transactions WHERE checkout_method = 'pos_extension');"
psql -U tabtracker -d tabtracker -h 127.0.0.1 \
  -c "DELETE FROM tab_tracker.transactions WHERE checkout_method = 'pos_extension';"
psql -U tabtracker -d tabtracker -h 127.0.0.1 \
  -c "DELETE FROM tab_tracker.tabs WHERE status IN ('sent','open');"
```

---

## References

- `docs/DEPLOYMENT.md` — Full production deployment steps, systemd config, nginx setup
- `docs/API.md` — Complete `/api/v1/*` endpoint reference with request/response schemas
- `docs/STATUS.md` — Current build state, verified/not-verified tables, gate verdicts
- `docs/TROUBLESHOOTING.md` — Known operational gotchas from the build
- `docs/QA_REPORT.md §3.1` — SPEC §8.2 test case matrix (original blocked tests)
- `docs/QA_REPORT.md §9` — Gate A verdict and details
