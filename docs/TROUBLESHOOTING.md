# Troubleshooting Guide — Tab Tracker POS Extension

**Last updated:** 2026-07-19
**Branch:** `feat/pos-extension` (HEAD 9fd346e)

Operational gotchas and tips discovered during the build. Read this before deploying, debugging, or extending. Saves the next person (or you-in-a-week) from rediscovering known issues.

---

## Table of Contents

1. [Port Conflict — DEV vs Production](#1-port-conflict--dev-vs-production)
2. [Modal.tsx Dev-Cred Fallback — Throws on PROD](#2-modaltsx-dev-cred-fallback--throws-on-prod)
3. [CORS — Default Is `*` for Pilot](#3-cors--default-is--for-pilot)
4. [X-API-Key — Every Endpoint Requires It](#4-x-api-key--every-endpoint-requires-it)
5. [Cart API — `addLineItem` Cannot Set Custom Price](#5-cart-api--addlineitem-cannot-set-custom-price)
6. [Migration Is Additive — No Destructive Rollback Needed](#6-migration-is-additive--no-destructive-rollback-needed)
7. [npm Vulnerabilities — 0 at Build Time](#7-npm-vulnerabilities--0-at-build-time)
8. [Pinned @shopify/ui-extensions-react Version](#8-pinned-shopifyui-extensions-react-version)
9. [Common Dev Workflow — `npm run dev`](#9-common-dev-workflow--npm-run-dev)
10. [Build Artifacts — Sourcemaps Contain Dev Strings](#10-build-artifacts--sourcemaps-contain-dev-strings)

---

## 1. Port Conflict — DEV vs Production

**Problem:** The production `tab-tracker` is served via gunicorn on **port 8095** (behind nginx on :8090). Starting a second backend instance on the same VPS on port 8095 fails with:

```
[Errno 98] Address already in use
```

This is what happened during QA — the agent's `uvicorn app:app` attempt crashed because prod was already bound to :8095.

**Fix:** Use an alternative port for DEV testing (e.g., **18095**):

```bash
export TAB_TRACKER_PORT=18095
uvicorn app:app --host 0.0.0.0 --port 18095
```

Better yet, use a separate VPS or a Docker container to avoid any port conflicts with production.

**Related:** The extension's `shopify.extension.toml [settings]` `backend_url` must point to the public HTTPS URL in production. For DEV, you can use the Tailscale IP (`http://100.122.187.17:18095`) or the public VPS IP on the alt port.

---

## 2. Modal.tsx Dev-Cred Fallback — Throws on PROD

**Problem:** `extension/src/Modal.tsx:81-85` has a module-level credential fallback:

```typescript
const api = createApiClient({
  baseUrl: "http://localhost:8095",
  apiKey: "test-key",
  shopLocationId: "dev-001",
});
```

In production builds (`import.meta.env.PROD`), this code throws intentionally — it's guarded to prevent shipping dev credentials to production. But if `backend_url` and `api_key` are not configured via `shopify.extension.toml [settings]` (or whatever runtime config mechanism is in place after the fix-iter), the extension will crash on load with no helpful error message.

**Fix:** Configure `[settings]` in `extension/shopify.extension.toml` **BEFORE** running `shopify app deploy`:

```toml
[settings]
backend_url = "https://your-public-endpoint.com"
api_key = "your-production-api-key"
default_terminal_id = "pos-terminal-1"
```

**If you see a blank screen or crash on POS:** Check that `[settings]` are populated. The extension reads them with `useSettings()` at startup.

**Current state:** SEC-001 (Critical) — hardcoded dev credentials in source. SEC-002 (High) — hardcoded terminal ID. These must be fixed before production deployment. See `docs/STATUS.md` open follow-ups.

---

## 3. CORS — Default Is `*` for Pilot

**Problem:** `config.py:34` sets default `POS_EXTENSION_ORIGIN = "*"` (wildcard). Combined with `allow_credentials=True` in `app.py:37-41`, this violates the HTTP Fetch spec (§3.2.2) — browsers must reject credentials on wildcard CORS.

**Impact for pilot:** Works fine because Shopify POS uses WebView which doesn't enforce CORS as strictly as browsers. But **must be locked down before production**:

```bash
# In production, set the concrete origin:
export POS_EXTENSION_ORIGIN=https://amsterdam-baking-company.myshopify.com
# Or if using Shopify Admin POS:
export POS_EXTENSION_ORIGIN=https://admin.shopify.com
```

When `POS_EXTENSION_ORIGIN` is a concrete value, the CORSMiddleware uses `allow_origins=[concrete_origin]` with `allow_credentials=True` — spec-compliant.

**Related:** See SEC-004 (Medium) in `docs/SECURITY_REPORT.md`.

---

## 4. X-API-Key — Every Endpoint Requires It

**Problem:** All 12 `/api/v1/*` endpoints are protected by `Depends(verify_api_key)` in `app.py:65-98`. Missing or invalid `X-API-Key` header → immediate 401.

```
curl -H "X-API-Key: your-key" http://localhost:8095/api/v1/products
```

**Gotchas:**
- The header name is literally `X-API-Key` (case-insensitive per HTTP spec, but use exact casing to be safe).
- The value must match `TAB_TRACKER_API_KEY` env var exactly.
- Query parameter auth is NOT supported for `/api/v1/*` endpoints (unlike the legacy `/exports/*` endpoints that use `_check_api_key()`).
- Auth fails **before** any DB query — you get a 401 even if the DB is down.

**Legacy endpoints** (`/`, `/admin`, `/history`, HTMX `/api/tabs/*`) do NOT use X-API-Key — they use session-cookie auth. This is intentional and unchanged.

---

## 5. Cart API — `addLineItem` Cannot Set Custom Price

**Problem:** The Shopify POS Cart API method `addLineItem(variantId, quantity, price)` appears to accept a price parameter in some docs, but **it does NOT accept a custom price** — it always uses the product's catalog price. This is confirmed per SPEC §3.5.

**Fix:** For items with `override_price` (price differs from catalog), use `addCustomSale({title, price, quantity, taxable})` instead:

```typescript
// In useCartApi.ts:78-98 — already implemented:
if (item.shopify_variant_id != null && !item.override_price) {
  cart.addLineItem(item.shopify_variant_id, item.quantity);
} else {
  cart.addCustomSale({
    title: item.name,
    price: item.override_price || item.unit_price,
    quantity: item.quantity,
    taxable: true,
  });
}
```

**Current state:** This logic exists in `useCartApi.ts` but is **not wired into Modal.tsx** (`handleSendToCart()` bypasses Cart API entirely — SEC-008). The `addCustomSale` fallback is correct per spec but never executed at runtime.

---

## 6. Migration Is Additive — No Destructive Rollback Needed

The migration `migrations/002_pos_extension.sql` is fully additive:
- `CREATE TABLE IF NOT EXISTS pos_sessions` — new table
- `ALTER TABLE tabs ADD COLUMN IF NOT EXISTS pos_cart_sent_at` — new column
- `ALTER TABLE tabs ADD COLUMN IF NOT EXISTS pos_terminal_id` — new column
- `ALTER TABLE transactions ADD COLUMN IF NOT EXISTS pos_order_id` — new column
- `ALTER TABLE transactions ADD COLUMN IF NOT EXISTS pos_terminal_id` — new column
- `ALTER TABLE transactions ADD COLUMN IF NOT EXISTS checkout_method` — new column

**No existing data is modified or dropped.** Existing web UI functionality (floor view, admin panel, history) is completely unaffected by these columns — they're never referenced in legacy queries.

**If you must rollback:**
```sql
DROP TABLE IF EXISTS tab_tracker.pos_sessions CASCADE;
ALTER TABLE tab_tracker.tabs DROP COLUMN IF EXISTS pos_cart_sent_at;
ALTER TABLE tab_tracker.tabs DROP COLUMN IF EXISTS pos_terminal_id;
ALTER TABLE tab_tracker.transactions DROP COLUMN IF EXISTS pos_order_id;
ALTER TABLE tab_tracker.transactions DROP COLUMN IF EXISTS pos_terminal_id;
ALTER TABLE tab_tracker.transactions DROP COLUMN IF EXISTS checkout_method;
```

This is safe — the web UI doesn't reference any of these columns.

---

## 7. npm Vulnerabilities — 0 at Build Time

At build time (2026-07-19), `npm install` in `extension/` reported **0 vulnerabilities**. If a future `npm install` surfaces any:

```bash
cd extension
npm audit
npm audit fix  # Auto-fix non-breaking vulnerabilities
npm audit fix --force  # May break deps — review carefully
```

The dependency chain is relatively shallow:
- `react@^18.3.0`
- `@shopify/ui-extensions-react@2025.7.4`
- `@shopify/ui-extensions@2025.7.4`
- Dev: `typescript@^5.5.0`, `vite@^5.4.0`, `@vitejs/plugin-react@^4.3.0`

---

## 8. Pinned `@shopify/ui-extensions-react` Version

The extension pins `@shopify/ui-extensions-react@2025.7.4` in `extension/package.json:23`.

**Do NOT upgrade this casually** — the Shopify POS UI Extensions API surface evolves rapidly. Breaking changes between versions include:
- Component renames/removals
- Hook API changes (`useSettings`, `useCartApi`, etc.)
- Target names (`pos.home.tile.render`, `pos.home.modal.render`)
- Sandbox permission model changes

**If you must upgrade:**
1. Check the [Shopify UI Extensions changelog](https://shopify.dev/docs/api/pos-ui-extensions/release-notes).
2. Compare the breaking changes between `2025.7` and your target.
3. Run `tsc --noEmit` and fix type errors.
4. Run `npm run build` and verify output.
5. Deploy to dev store and test on POS device **before** promoting to production.

---

## 9. Common Dev Workflow — `npm run dev`

The standard development loop for the extension:

```bash
cd extension
npm install                          # One-time setup
npm run dev                          # Start Shopify CLI + Vite watcher
```

`npm run dev` does two things:
1. Launches the Vite dev server (hot-reloads TypeScript changes).
2. Opens a tunnel via Shopify CLI so your dev store can load the extension.

**Hot-reload behavior:** Changes to `extension/src/*.tsx` trigger a rebuild. The POS device (if on the same network) should reload automatically after ~1-2 seconds.

**If the tunnel doesn't start:**
- Verify `shopify version` is v3.x.
- Verify `shopify whoami` shows authentication against the right store.
- Check if your network blocks ngrok/Cloudflare tunnel (some corporate networks do).
- Try `shopify app dev --tunnel-url <custom-tunnel>` if you have a pre-configured tunnel.

**For POS device testing:**
- The extension must be installed on the dev store (see `docs/DEPLOYMENT.md §2`).
- POS devices must be assigned to the dev store in Shopify Admin.
- After `npm run dev` changes, re-open the Tab Tracker modal on the POS device to pick up changes.

---

## 10. Build Artifacts — Sourcemaps Contain Dev Strings

**Problem:** `extension/dist/*.js.map` files contain source map content that includes development strings (including the dev credentials from Modal.tsx if they haven't been removed yet):

```
extension/dist/Modal.js.map → contains "http://localhost:8095", "test-key", "dev-001"
```

**Is this a problem?** **No** — sourcemaps are never loaded at runtime in production. They're only used by browser devtools for debugging. The production `dist/*.js` files are clean (Vite's dead-code elimination removes the guarded `import.meta.env.PROD` fallback):

```bash
# Verify runtime artifacts are clean:
grep --only-matching "test-key\|localhost:8095\|dev-001" extension/dist/*.js
# Expected: 0 matches
```

**Recommendation:** If you're paranoid about sourcemap leaks:
1. Remove `dist/extension/dist/Modal.js.map` from the deployment artifact.
2. Or configure `vite.config.ts` to disable sourcemaps in production: `build.sourcemap = false`.

**Better fix:** Remove the hardcoded credentials from Modal.tsx entirely (SEC-001 fix) and rebuild. Then sourcemaps won't contain them either.

---

## Quick Reference

| Problem | Symptom | Fix |
|---------|---------|-----|
| Port in use | `[Errno 98] Address already in use` | Use port `18095` for DEV |
| Extension crashes on POS | Blank screen or JS error | Configure `[settings]` in `shopify.extension.toml` |
| CORS errors in browser console | `Access-Control-Allow-Origin` missing | Set `POS_EXTENSION_ORIGIN` to concrete origin |
| API returns 401 | Auth rejected | Check `X-API-Key` header matches `TAB_TRACKER_API_KEY` |
| Cart items show catalog price, not override | Wrong price in cart | Use `addCustomSale` for override-price items (see §5) |
| Migration fails | Syntax error or missing `IF NOT EXISTS` | Migration is idempotent — safe to re-run |
| npm audit shows vulnerabilities | Security warnings | `npm audit fix` (see §7) |
| Extension build fails after upgrade | TypeScript errors | Check `@shopify/ui-extensions-react` compatibility (see §8) |

---

## References

- `docs/DEPLOYMENT.md` — Full deployment guide (backend + extension)
- `docs/API.md` — All 12 `/api/v1/*` endpoints with request/response schemas
- `docs/STATUS.md` — Current build status, verified/not-verified, gate verdicts
- `docs/TESTING.md` — Live test plan with checklist
- `docs/SECURITY_REPORT.md` — Full security audit (17 findings)
- `docs/QA_REPORT.md` — QA pass/fail matrix
