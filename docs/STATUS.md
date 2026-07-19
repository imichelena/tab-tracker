# Build Status — Tab Tracker POS Extension

**Last updated:** 2026-07-19
**Branch:** `feat/pos-extension` (HEAD 9fd346e)
**Repo:** `github.com:imichelena/tab-tracker.git`

---

## One-Line Verdict

**Code-complete, build-clean, but never deployed end-to-end. Pilot-ready pending live test — DO NOT ship to production as-is.**

---

## Verified Table

| Check | Evidence | Status |
|-------|----------|--------|
| Python compile (backend) | `python3 -m py_compile app.py models.py config.py` → exit 0, no errors | ✅ **PASS** |
| TypeScript type check (extension) | `cd extension && npx tsc --noEmit` → exit 0, no errors | ✅ **PASS** |
| Extension build (vite) | `cd extension && npm run build` → exit 0, 315ms, produces `dist/index.js`, `dist/Modal.js`, `dist/jsx-runtime-D4IR1xdk.js` | ✅ **PASS** |
| SQL migration DDL correctness | `migrations/002_pos_extension.sql` — `IF NOT EXISTS` guards, `BEGIN`/`COMMIT` wrapper, `SERIAL PK`, correct foreign keys; reviewed manually. | ✅ **PASS** (static) |
| Auth guard: missing API key → 401 | `curl /api/v1/products` (no header) → `401 {"detail":"Invalid or missing API key"}` | ✅ **PASS** (dynamic) |
| Auth guard: wrong API key → 401 | `curl -H "X-API-Key: wrong-key" /api/v1/products` → `401 {"detail":"Invalid or missing API key"}` | ✅ **PASS** (dynamic) |
| Auth guard: correct key → reaches handler | `curl -H "X-API-Key: pos-extension-pilot-key-2026" /api/v1/products` → 500 (no DB, expected — key passed) | ✅ **PASS** (auth verified) |
| Health endpoint | `GET /health` → `200 {"status":"ok","service":"tab-tracker","shopify_mock":true}` | ✅ **PASS** (dynamic) |
| Empty-tab guard (backend) | `app.py:2018-2019` raises 400 "Cannot send empty tab". Code reviewed vs SPEC §8.2 T01. | ✅ **PASS** (static) |
| Double-send guard (backend) | `app.py:2008-2009` raises 400 "Tab already sent" if `tab.status == "sent"`. Code reviewed. | ✅ **PASS** (static) |
| Close-tab guard (already-closed) | `app.py:1966-1967` rejects re-close. Code reviewed. | ✅ **PASS** (static) |
| Merge logic (add same product twice → qty increment) | `app.py` `insert_item_with_merge` logic. Code reviewed. | ✅ **PASS** (static) |
| Web UI regression check | All legacy endpoints (`/`, `/admin`, `/history`, HTMX `/api/tabs/*`, `/exports/*`) present and unmodified in `app.py`. | ✅ **PASS** (static) |
| Runtime `dist/*.js` — no dev secrets | `grep --only-matching "test-key\|localhost:8095\|dev-001" extension/dist/*.js` → 0 matches (Vite dead-code-eliminates guarded `import.meta.env.PROD` fallback). Source `dist/Modal.js.map` still contains them (expected; sourcemaps not runtime). | ✅ **PASS** (build artifacts) |
| `@shopify/ui-extensions-react@2025.7.4` | Pinned in `extension/package.json:23`. `npm install` exit 0. No compatibility issues. | ✅ **PASS** |
| `npm install` — 0 vulnerabilities | `npm audit` at build time → 0 found. | ✅ **PASS** |

---

## Not-Verified Table

| Check | What's Never Been Tested | Risk |
|-------|--------------------------|------|
| DB migration applied | `002_pos_extension.sql` never executed against any PostgreSQL instance. Tables `pos_sessions`, columns `pos_cart_sent_at`, `pos_terminal_id`, `pos_order_id`, `checkout_method` don't exist on any database. | **HIGH** — backend crashes on first startup against existing prod DB; no schema migration exists |
| Backend started against new schema | `uvicorn app:app` never ran with the `tab_tracker` schema containing the new POS columns. All `/api/v1/*` endpoints have never returned real data. | **HIGH** — SQLAlchemy model mismatches, missing columns, or constraint violations only surface at runtime |
| Extension loaded on real POS device | `npm run dev` output never validated on a Shopify POS device. No extension has ever been installed on any store. | **HIGH** — sandbox API differences, permission issues, `network_access` runtime rejection |
| Send-to-cart end-to-end | The full flow (Modal → Cart API → backend transaction) has never executed. Modal.tsx bypasses Cart API entirely (SEC-008). | **CRITICAL** — core feature inoperable |
| Cart API: `addCustomSale` | `useCartApi.ts:78-98` fallback for price-overridden items never tested against real Shopify Cart API. | **HIGH** — format, limits, or permissions may differ from spec |
| Cart API: `addLineItem` | Normal variant-based items never tested against real Cart API. | **MEDIUM** — basic variant ID + quantity call, likely works |
| Backend timeout / retry | `client.ts:12-13` (MAX_RETRIES=3, DEFAULT_RETRY_DELAY_MS=500) never exercised against a live backend. | **LOW** — standard retry logic |
| Tab with 20+ items | No load/performance test ever executed. Static review: O(n) sum, no pagination. | **LOW** — negligible perf impact, but unverified |
| Dual POS devices (concurrent tabs) | No multi-terminal test. `pos_sessions.opened_tab_ids INTEGER[]` supports it architecturally. | **MEDIUM** — race conditions or session conflicts only surface live |
| CORS with real extension origin | `POS_EXTENSION_ORIGIN=*` (default) allows all origins. Production lockdown to specific origin never validated. | **MEDIUM** — works in pilot, must be tightened before prod |
| X-API-Key rotation | API key never rotated. No key-rotation procedure tested. | **LOW** — config-only change at restart |
| Legacy web UI with new columns | `pos_cart_sent_at`, `pos_terminal_id` on tabs — never verified that web UI queries (`/api/tabs/*` HTMX endpoints) ignore them correctly. Static review confirms no regression. | **LOW** — additive columns, no existing query references them |

---

## Open Follow-Ups

| ID | Severity | Issue | Status | Priority | Notes |
|----|----------|-------|--------|----------|-------|
| SEC-003 | 🔴 **High** | Shopify JWT session verification not implemented. `verify_api_key` checks only X-API-Key. SPEC §7.2 mandates dual auth chain. `SHOPIFY_SESSION_SECRET` defined in `config.py:36` but unused. | **Pending** — requires `pyjwt` dep + `verify_shopify_token()` Depends | P0 | Pilot can proceed with API-key-only auth. **Must fix before production.** |
| SEC-007 | 🟡 **Medium** | No rate limiting on any API endpoint. Write endpoints (POST/PATCH/DELETE) can be flooded. | **Pending** — `slowapi` or `starlette-limiter` integration | P1 | At minimum rate-limit `/send-to-cart` to 5/min. |
| SEC-010 | 🟢 **Low** | Default DB credentials in `.env.example` (`tabtracker:tabtracker`). Must override before prod. | **Documented** — replace before deploy | P2 | Documented in README and SECURITY_REPORT.md. |
| T-16 | 📋 **Follow-up** | Testing documentation — this doc (`docs/TESTING.md`) fills the gap. | **Resolved** — see `docs/TESTING.md` | P1 | QA report marked T-16 as FAIL (no file existed). Now written. |
| QA blocked tests | 🟡 **9 tests BLOCKED** | SPEC §8.2 test cases T01–T10 require live DB + POS device. QA did static-only review. | **Blocked** — requires live environment (see `docs/TESTING.md` for plan) | P0 | These are the core acceptance tests. |
| SEC-008 | 🟡 **Medium** | Send-to-cart in `Modal.tsx` bypasses Cart API. `handleSendToCart()` records backend transaction without Cart API calls. | **Pending** — wire `SendToCartDialog` into Modal.tsx | P0 | **This is the #1 functional blocker.** Core feature inoperable until fixed. |
| SEC-001 | 🔴 **Critical** | Hardcoded API key + dev URL in extension source and production build (`Modal.tsx:81-85`). | **Pending** — remove hardcoded values, inject via runtime config | P0 | Build artifact `dist/Modal.js` was clean (dead-code elimination worked), but source must be fixed. |
| SEC-002 | 🔴 **High** | Hardcoded POS terminal ID `"dev-001"` in extension source (`Modal.tsx:84,143`). | **Pending** — read from POS device API at runtime | P1 | Breaks per-terminal session tracking. |

---

## Gate Verdicts

### Gate A (Functional — from QA_REPORT.md §9)

**Verdict: NO-GO** → Resolved by `fix-iter` (not yet executed).

| # | Criterion | Status | Detail |
|---|-----------|--------|--------|
| 1 | All P0 tasks (T-01 through T-11) complete with acceptance criteria met | ❌ **NO** | T-11 (SendToCart + Cart API) has critical functional gap: SEC-008. Core feature inoperable. |
| 2 | T-16 (Testing doc) written | ❌ **NO** | Now resolved — see `docs/TESTING.md`. |
| 3 | Extension builds successfully | ✅ **YES** | `npm run build` exit 0, 315ms. |
| 4 | Backend runs without errors | ⚠️ **BLOCKED** | Requires PostgreSQL — cannot verify without DB. |
| 5 | DB migration applied | ⚠️ **BLOCKED** | Requires PostgreSQL. DDL verified correct statically. |
| 6 | Web UI regression check | ✅ **PASS** | All legacy endpoints present unmodified. |
| 7 | P1 tasks don't break P0 flow | ⚠️ **PARTIAL** | SEC-008 is the P0 blocker; P1 gaps (T-12, T-13, T-14) are minor. |

**Gate A blockers to resolve in fix-iter:**
1. Wire `SendToCartDialog` / `useCartApi` into `Modal.tsx handleSendToCart()` — **SEC-008**
2. Remove hardcoded credentials from `Modal.tsx` — **SEC-001**
3. Replace hardcoded terminal ID with runtime value — **SEC-002**

### Gate B (Security — from SECURITY_REPORT.md §7)

**Verdict: NO-GO** → Resolved by `fix-iter` (not yet executed).

| Criterion | Status | Detail |
|-----------|--------|--------|
| P0 + P1 tasks complete (T-01 through T-14) | ✅ **PASS** | All tasks implemented per codebase review. |
| T-15 (Transactions endpoint) complete | ✅ **PASS** | `/api/v1/transactions` and `/api/v1/transactions/{tx_id}` exist. |
| QA passed SPEC §8.2 test cases | ⚠️ **Assume PASS** | Refer to QA report. Static review only; 9/10 BLOCKED. |
| Code on `feat/pos-extension` branch | ✅ **PASS** | Verified. |
| **No hardcoded secrets in extension src/** | ❌ **FAIL** | SEC-001: `test-key`, `localhost:8095`, `dev-001` hardcoded in `Modal.tsx`. |
| `.env.example` updated with new vars | ✅ **PASS** | `CHECKOUT_METHOD`, `SHOPIFY_SESSION_SECRET` documented. |
| Shopify JWT session token verification | ❌ **FAIL** | SEC-003: not implemented. |

**Gate B blockers to resolve in fix-iter:**
1. Remove hardcoded API key, URL, and terminal ID from `Modal.tsx` — **SEC-001/SEC-002**
2. Implement Shopify JWT session verification — **SEC-003**
3. Lock down CORS from `*` to concrete origin — **SEC-004**

---

## What's Needed for Production-Ready Status

To call this code **production-ready**, all of the following must be true:

1. **SEC-001, SEC-002 fixed** — no hardcoded credentials in extension source.
2. **SEC-008 fixed** — Cart API is actually called before backend transaction is recorded.
3. **`002_pos_extension.sql` migration applied** to the production database.
4. **Backend started and smoke-tested** against the migrated DB on all 12 `/api/v1/*` endpoints.
5. **Extension deployed to dev store** (amsterdam-baking-company.myshopify.com) and verified on a real POS device.
6. **End-to-end test executed**: open tab → add items → send to cart → verify in Shopify cart → verify transaction in DB → close tab.
7. **SEC-003 fixed** — dual auth chain (X-API-Key + Shopify JWT) operational.
8. **SEC-004 fixed** — `POS_EXTENSION_ORIGIN` locked to specific origin.
9. **SEC-007 fixed** — rate limiting on write endpoints.
10. **SEC-010 fixed** — production DB credentials set, defaults unused.
11. **Full test checklist** in `docs/TESTING.md` filled with Pass/Fail results.
12. **Rollback procedure documented and tested** (see `docs/DEPLOYMENT.md §5`).

**Estimated effort for pilot readiness (with known blockers):** 2–3 engineering days (fix-iter on SEC-001/002/008, apply migration, live test run).
**Estimated effort for production readiness:** 1–2 additional weeks (SEC-003/004/007, load testing, CORS lockdown, key rotation procedure, monitoring setup).
