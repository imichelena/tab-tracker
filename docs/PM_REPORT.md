# PM Report — Tab Tracker POS Extension (Phase 1)

**Generated:** 2026-07-18  
**Inputs:** `docs/SPEC.md` (509 lines), `docs/BUILD_PLAN.md` (253 lines), existing codebase  
**Branch:** `feat/pos-extension`  
**Pipeline:** Phase 1 → Phase 2 (Build) → Phase 3 (QA) → Phase 4 (Security) → Phase 5 (Docs)

---

## 1. Executive Summary

This project ports the existing Tab Tracker web application (a bakery floor tab-management system) into a **Shopify POS UI Extension** that embeds directly into the POS interface, replacing the current draft-order workaround. The extension uses `pos.home.tile.render` and `pos.home.modal.render` targets to provide table tab tracking, product selection by category, price-override support, and a "Send to POS Cart" flow that pushes items directly into the native Shopify POS cart via the Cart API (`addLineItem`, `addCustomSale`, `clearCart`, `applyCartDiscount`, `setCustomer`). The backend (FastAPI on VPS) gets 12 new `/api/v1/*` endpoints, a new `pos_sessions` DB table, and column additions to `tabs` and `transactions` tables. The existing web UI (floor.html, admin.html, history.html) and the draft-order fallback (`CHECKOUT_METHOD=draft_order`) remain fully intact. This is a single-shop pilot using a custom (unlisted) Shopify app — not an App Store distribution.

---

## 2. Refined Task Table

### T-01 — DB Migration: pos_sessions table + column additions

| Field | Value |
|---|---|
| **Description** | Create `migrations/002_pos_extension.sql` with: (1) new `tab_tracker.pos_sessions` table (per SPEC §3.7), (2) `ALTER TABLE tab_tracker.tabs ADD COLUMN pos_cart_sent_at TIMESTAMPTZ, pos_terminal_id VARCHAR(100)`, (3) `ALTER TABLE tab_tracker.transactions ADD COLUMN pos_order_id VARCHAR(100), pos_terminal_id VARCHAR(100), checkout_method VARCHAR(20) DEFAULT 'pos_extension'`. Update `models.py` with `PosSession` SQLAlchemy model referencing `tab_tracker.pos_sessions`. Add new columns to existing `Tab` and `Transaction` SQLAlchemy models. |
| **Files** | `migrations/002_pos_extension.sql` (create), `models.py` (modify) |
| **Dependencies** | None (can start immediately) |
| **Priority** | **P0** — all backend tab/send endpoints depend on the new schema |
| **Effort** | **S** — 1 SQL migration file (~30 lines) + model additions (~40 lines). Straightforward DDL. |
| **Acceptance criteria** | 1. `psql -U tabtracker -d tabtracker -f migrations/002_pos_extension.sql` exits 0 2. `\dt tab_tracker.pos_sessions` shows the table 3. `\d tab_tracker.tabs` shows `pos_cart_sent_at` and `pos_terminal_id` columns 4. `\d tab_tracker.transactions` shows `pos_order_id`, `pos_terminal_id`, `checkout_method` columns 5. Python `from models import PosSession` imports without error 6. `Tab.pos_cart_sent_at` and `Transaction.checkout_method` are accessible as SQLAlchemy column attributes |
| **Agent type** | Backend |
| **Workstream** | A |
| **SPEC reference** | §3.7 Database Changes |

---

### T-02 — Backend: `/api/v1/products` + `/api/v1/categories` endpoints

| Field | Value |
|---|---|
| **Description** | Add two read-only JSON endpoints to `app.py`. `GET /api/v1/products` returns all active products with category name and active price override info. `GET /api/v1/categories` returns all active categories ordered by `sort_order`. Both scoped to the current shop (single shop for pilot). Responses must include fields needed by the POS extension: product id, name, price, category_id, shopify_variant_id, image_path, override_price (if any), category name. |
| **Files** | `app.py` (modify — add 2 routes) |
| **Dependencies** | T-05 (auth middleware — routes must be protected) |
| **Priority** | **P0** — extension's product catalog depends on these endpoints |
| **Effort** | **S** — two simple SELECT queries per endpoint. ~50 lines total. |
| **Acceptance criteria** | 1. `curl -H "X-API-Key: test-key" http://localhost:8095/api/v1/products` returns HTTP 200 with JSON array of products 2. Each product object includes: `id`, `name`, `price`, `category_id`, `category_name`, `shopify_variant_id`, `image_path`, `override_price` (nullable) 3. `GET /api/v1/categories` returns array ordered by `sort_order` 4. Inactive products are excluded 5. Missing API key returns 401 6. Existing web UI `/` (floor) still renders correctly |
| **Agent type** | Backend |
| **Workstream** | A |
| **SPEC reference** | §3.4 New Endpoints |

---

### T-03 — Backend: `/api/v1/tables` + `/api/v1/tabs` CRUD endpoints

| Field | Value |
|---|---|
| **Description** | Add routes to `app.py`: `GET /api/v1/tables` (active tables for current shop), `GET /api/v1/tabs?table_id=N` (open tab + items for a table), `POST /api/v1/tabs` (open new tab creating a pos_session record), `POST /api/v1/tabs/{tab_id}/items` (add item, merging identical product+price), `DELETE /api/v1/tabs/{tab_id}/items/{item_id}`, `PATCH /api/v1/tabs/{tab_id}/items/{item_id}` (update qty, deleting if qty<=0), `GET /api/v1/tabs/open` (all open tabs), `POST /api/v1/tabs/{tab_id}/close` (close tab). Must create a `pos_sessions` row when opening a tab, tracking `pos_terminal_id`. Must handle single-shop scoping. |
| **Files** | `app.py` (modify — add 8 routes) |
| **Dependencies** | T-01 (pos_sessions table + new tab columns must exist) |
| **Priority** | **P0** — tab management is core to the extension |
| **Effort** | **M** — 8 endpoints across tab creation, item CRUD, and session tracking. ~200 lines. Complexity from merging same product+price items (matching existing web UI behavior at app.py lines 234-246) and session creation logic. |
| **Acceptance criteria** | 1. `POST /api/v1/tabs` with `{"table_id": 1, "pos_terminal_id": "dev-001"}` returns 201 with tab id 2. `GET /api/v1/tabs?table_id=1` returns open tab with items array 3. `POST /api/v1/tabs/{id}/items` with `{"product_id": 5}` adds item, merges duplicate product+price 4. `DELETE /api/v1/tabs/{id}/items/{item_id}` removes item, recalculates 5. `PATCH /api/v1/tabs/{id}/items/{item_id}` with `{"quantity": 3}` updates qty; qty<=0 deletes 6. `GET /api/v1/tabs/open` returns all open tabs across all tables 7. `POST /api/v1/tabs/{id}/close` sets status='closed' 8. Missing API key returns 401 9. Existing web UI tab operations (`/api/tabs/*` HTMX endpoints) continue to work |
| **Agent type** | Backend |
| **Workstream** | A |
| **SPEC reference** | §3.4 New Endpoints, §3.7 pos_sessions table |

---

### T-04 — Backend: `/api/v1/tabs/{tab_id}/send-to-cart` endpoint

| Field | Value |
|---|---|
| **Description** | Add `POST /api/v1/tabs/{tab_id}/send-to-cart` to `app.py`. This endpoint: (1) validates tab is open and has items, (2) prevents double-send (tab already "sent"), (3) creates a `Transaction` record with `checkout_method='pos_extension'`, (4) snapshots `TransactionItem` rows from tab items (mirroring existing logic at app.py lines 431-471), (5) sets `tab.status = 'sent'`, `tab.pos_cart_sent_at = now()`, `tab.pos_terminal_id`, (6) returns the transaction id. Does NOT call Shopify (Cart API is client-side; this is purely a server-side record of the action). |
| **Files** | `app.py` (modify — add 1 route, reuse existing transaction-snapshotting logic) |
| **Dependencies** | T-01 (new transaction columns), T-03 (tab CRUD must exist for context) |
| **Priority** | **P0** — the send-to-cart flow is the core feature |
| **Effort** | **S** — mostly reuses existing transaction creation pattern from app.py lines 382-471. ~80 lines. |
| **Acceptance criteria** | 1. `POST /api/v1/tabs/{id}/send-to-cart` with valid open tab+items returns 200 with `{"transaction_id": N}` 2. Tab status changes to "sent" in DB 3. Transaction record is created with `checkout_method='pos_extension'` 4. TransactionItem snapshots match tab items 5. Re-sending the same tab returns 400 "Tab already sent" 6. Sending an empty tab returns 400 "Cannot send empty tab" 7. Missing API key returns 401 8. Existing `/api/tabs/{tab_id}/send-to-shopify` (draft order route) continues to work unchanged |
| **Agent type** | Backend |
| **Workstream** | A |
| **SPEC reference** | §3.4, §3.6 Data Flow — "Send to POS Cart" |

---

### T-05 — Backend: API key auth middleware for `/api/v1/*`

| Field | Value |
|---|---|
| **Description** | Add a FastAPI middleware or dependency to `app.py` that enforces `X-API-Key` header on all `/api/v1/*` routes. The existing `_check_api_key()` helper (app.py line 1139) is per-endpoint — refactor it into a reusable `Depends`-based dependency so new routes use `Depends(verify_api_key)`. Add `X-Shop-Location` header support (maps to `shop_id`). Add `CHECKOUT_METHOD` config support to `config.py`. Must NOT affect existing endpoints (`/api/tabs/*`, `/admin/*`, `/`, `/health`, `/login`). |
| **Files** | `app.py` (modify — add dependency), `config.py` (modify — add `CHECKOUT_METHOD` and `SHOPIFY_SESSION_SECRET` env vars) |
| **Dependencies** | None (can start immediately — pure middleware) |
| **Priority** | **P0** — all new endpoints require auth guard |
| **Effort** | **S** — single dependency function + header parsing. ~40 lines. |
| **Acceptance criteria** | 1. All `/api/v1/*` endpoints return 401 when `X-API-Key` header is missing 2. Valid key returns normal response 3. Existing `/health`, `/login`, `/`, `/admin/*`, `/api/tabs/*` continue without requiring API key 4. `POST /api/v1/tabs` with `X-API-Key` + `X-Shop-Location: dev-001` resolves to internal shop_id 5. `CHECKOUT_METHOD` defaults to `'pos_extension'` when env var is unset 6. Config env vars for `SHOPIFY_SESSION_SECRET` and `CHECKOUT_METHOD` are documented in `.env.example` |
| **Agent type** | Backend |
| **Workstream** | A |
| **SPEC reference** | §3.4 Authentication, §7.2 Requirements, §7.3 Secrets Management |

---

### T-06 — Extension scaffold: project structure + config files

| Field | Value |
|---|---|
| **Description** | Create the `extension/` directory from scratch with: `shopify.extension.toml` (pos_ui_extension type, targets pos.home.tile.render and pos.home.modal.render, network_access=true), `package.json` (React/Preact, @shopify/pos-app-sdk, vite, typescript), `tsconfig.json`, `vite.config.ts`, `src/types/index.ts` (TypeScript interfaces for Product, Category, Tab, TabItem, Transaction). Set up Shopify CLI project pattern. |
| **Files** | `extension/shopify.extension.toml` (create), `extension/package.json` (create), `extension/tsconfig.json` (create), `extension/vite.config.ts` (create), `extension/src/types/index.ts` (create) |
| **Dependencies** | None |
| **Priority** | **P0** — extension cannot exist without scaffold |
| **Effort** | **S** — boilerplate config files, ~5 files, ~100 lines total. Straightforward TOML/JSON/TypeScript. |
| **Acceptance criteria** | 1. `extension/shopify.extension.toml` is valid TOML with correct `pos_ui_extension` type and both targets 2. `extension/package.json` has valid JS deps (react, react-dom, @shopify/pos-app-sdk, vite, typescript, @types/react) 3. `npm install` in `extension/` succeeds with no errors 4. TypeScript types compile with `npx tsc --noEmit` 5. `src/types/index.ts` defines: `Product`, `Category`, `Tab`, `TabItem`, `Transaction`, `CartItem`, `SendToCartResult` |
| **Agent type** | Extension-Scaffold |
| **Workstream** | B |
| **SPEC reference** | §3.2 POS Extension Structure, §3.3 Extension Targets, §4.2 POS Extension Capabilities |

---

### T-07 — Extension: home tile + modal shell

| Field | Value |
|---|---|
| **Description** | Create `src/index.tsx` (pos.home.tile.render — renders a `s-tile` component showing "Tab Tracker" with open tab count badge). Create `src/modal.tsx` (pos.home.modal.render — full-screen `s-modal` shell with left panel placeholder for ProductGrid and right panel placeholder for TabBill, sticky bottom "Send to POS Cart" button). Wire both to `shopify.extension.toml` targets. Use Shopify web components (`s-tile`, `s-modal`, `s-button`, `s-badge`, `s-spinner`). |
| **Files** | `extension/src/index.tsx` (create), `extension/src/modal.tsx` (create), `extension/src/styles/extension.css` (create) |
| **Dependencies** | T-06 (scaffold must exist) |
| **Priority** | **P0** — extension must render in POS to be visible |
| **Effort** | **S** — tile is ~20 lines, modal shell is ~80 lines. Simple component wiring. |
| **Acceptance criteria** | 1. `index.tsx` exports a component rendering `s-tile` with title "Tab Tracker" 2. `modal.tsx` exports a component rendering `s-modal` with two panel placeholders 3. `shopify.extension.toml` correctly references both modules 4. `extension.css` includes basic layout styles 5. `npm run build` succeeds without errors 6. Modal placeholder shows category pills area + product grid area + tab bill area + "Send to POS Cart" button |
| **Agent type** | Extension-UI |
| **Workstream** | C |
| **SPEC reference** | §3.3 Extension Targets, §5.1 POS Home Tile, §5.2 Modal — Main View, §5.5 Component Constraints |

---

### T-08 — Extension: API client

| Field | Value |
|---|---|
| **Description** | Create `src/api/client.ts` — a fetch-based API client that: (1) calls backend endpoints at the configured base URL, (2) attaches `X-API-Key` and `X-Shop-Location` headers (API key from Shopify app metafield or env, location from `pos.device.api`), (3) handles JSON responses, (4) exposes typed methods: `getProducts()`, `getCategories()`, `getTables()`, `getTabs(tableId)`, `openTab(tableId)`, `addItem(tabId, productId)`, `removeItem(tabId, itemId)`, `updateItemQty(tabId, itemId, qty)`, `sendToCart(tabId)`, `closeTab(tabId)`, `getOpenTabs()`. Create `src/hooks/useProducts.ts` (fetch products, cache) and `src/hooks/useTabs.ts` (tab CRUD state management). |
| **Files** | `extension/src/api/client.ts` (create), `extension/src/hooks/useProducts.ts` (create), `extension/src/hooks/useTabs.ts` (create) |
| **Dependencies** | T-05 (auth middleware — API client must match auth header format), T-02 (products/categories endpoints), T-03 (tabs CRUD endpoints — `useTabs` hook depends on these) |
| **Priority** | **P0** — extension cannot function without backend communication |
| **Effort** | **S** — single API client class + 2 React hooks. ~150 lines total. |
| **Acceptance criteria** | 1. `client.ts` exports a configured client with all typed methods above 2. `getProducts()` calls `GET /api/v1/products` with correct headers 3. `useProducts` hook returns `{products, categories, loading, error}` 4. `useTabs` hook returns `{tabs, activeTab, addItem, removeItem, updateQty, sendToCart, closeTab, loading, error}` 5. API key is not hardcoded in source — read from runtime config 6. All fetch errors are caught and surfaced as typed error objects |
| **Agent type** | Extension-UI |
| **Workstream** | C |
| **SPEC reference** | §3.4 API Endpoints, §3.4 Authentication, §7.3 Secrets Management |

---

### T-09 — Extension: CategoryBar + ProductGrid components

| Field | Value |
|---|---|
| **Description** | Create `src/components/CategoryBar.tsx` — horizontal scroll of `s-select` or `s-badge` pills for category filtering. Create `src/components/ProductGrid.tsx` — 3-4 column grid of `s-card` product tiles from filtered category. Create `src/components/ProductCard.tsx` — individual product card showing image (if available), name, price (showing override price if different from base), tap handler to add to tab. Wire into `modal.tsx` left panel. |
| **Files** | `extension/src/components/CategoryBar.tsx` (create), `extension/src/components/ProductGrid.tsx` (create), `extension/src/components/ProductCard.tsx` (create) |
| **Dependencies** | T-08 (API client for product/category data) |
| **Priority** | **P0** — product selection is core UX |
| **Effort** | **M** — 3 interlinked components with filtering, grid layout, and tap handling. ~250 lines. |
| **Acceptance criteria** | 1. `CategoryBar` renders active category pills from `getCategories()` 2. Tapping a category pill filters the product grid to that category 3. "All" (or first pill) shows all products 4. `ProductCard` shows product name, price, and override price (if different) 5. Tapping a product card fires `onProductSelect(productId)` callback 6. Products without images render a placeholder 7. Grid re-renders efficiently on category change |
| **Agent type** | Extension-UI |
| **Workstream** | C |
| **SPEC reference** | §5.2 Modal — Main View (left panel) |

---

### T-10 — Extension: TabBill + tab item management

| Field | Value |
|---|---|
| **Description** | Create `src/components/TabBill.tsx` — right panel showing: table selector (`s-select`), current tab items in scrollable `s-list` (product name, qty with inc/dec controls, unit price, line total, delete button), running total, notes field (`s-text-field`). Wire item add/remove/qty to `useTabs` hook. Handle quantity increment (merge same product+price), decrement (delete at 0), and full delete. |
| **Files** | `extension/src/components/TabBill.tsx` (create) |
| **Dependencies** | T-08 (API client for tab CRUD via `useTabs` hook), T-03 (backend tab CRUD must be operational) |
| **Priority** | **P0** — tab bill is core UX component |
| **Effort** | **M** — table selector, item list with controls, running total calculation, notes handling. ~200 lines. |
| **Acceptance criteria** | 1. Table selector dropdown populated from `getTables()` 2. Selecting a table creates/opens a tab 3. Adding a product (from ProductGrid) shows in bill immediately 4. Tapping inc/dec adjusts quantity; dec to 0 removes item 5. Delete button removes item from bill 6. Running total updates on every change 7. Notes field persists text to tab via API 8. Empty state shows "Select a table to start" 9. "Send to POS Cart" button is disabled when tab is empty or already sent |
| **Agent type** | Extension-UI |
| **Workstream** | C |
| **SPEC reference** | §5.2 Modal — Main View (right panel), §5.3 Modal — Tab List View |

---

### T-11 — Extension: SendToCart — Cart API integration

| Field | Value |
|---|---|
| **Description** | Create `src/components/SendToCart.tsx` — confirmation modal and Cart API integration. Logic (per SPEC §3.5): (1) check if POS cart is empty via Cart API, (2) if not empty, show `s-banner` warning "Cart has existing items. Clear and replace?", (3) call `shopify.cart.clearCart()` if user confirms, (4) iterate tab items: if `priceOverride` exists call `shopify.cart.addCustomSale()`, else call `shopify.cart.addLineItem(shopifyVariantId, quantity)`, (5) if variant ID missing, fallback to `addCustomSale`, (6) call `applyCartDiscount()` if discount present, (7) call `setCustomer()` if customer attached, (8) after successful cart fill, call `POST /api/v1/tabs/{id}/send-to-cart` to record transaction server-side, (9) show success `s-banner` with auto-close. Create `src/hooks/useCartApi.ts` — typed wrapper around `@shopify/pos-app-sdk` Cart API methods. |
| **Files** | `extension/src/components/SendToCart.tsx` (create), `extension/src/hooks/useCartApi.ts` (create) |
| **Dependencies** | T-10 (TabBill component — provides tab items to send), T-04 (send-to-cart backend endpoint must exist), T-08 (API client for POST send-to-cart) |
| **Priority** | **P0** — this is the core integration feature |
| **Effort** | **L** — complex Cart API integration with 5+ API calls, error handling for each, fallback logic, confirmation flow. ~300 lines. |
| **Acceptance criteria** | 1. `useCartApi` wraps `clearCart()`, `addLineItem()`, `addCustomSale()`, `applyCartDiscount()`, `setCustomer()` from `@shopify/pos-app-sdk` 2. Items with `priceOverride` use `addCustomSale` with override price (per SPEC §3.5) 3. Items without override use `addLineItem` with `shopifyVariantId` 4. Items without `shopifyVariantId` fall back to `addCustomSale` with product name + price (per SPEC §6) 5. Non-empty cart shows confirmation warning before clearing 6. Each Cart API failure shows which item failed, skips it, continues 7. After all Cart API calls succeed, `POST /api/v1/tabs/{id}/send-to-cart` is called 8. Result shows success banner with item count and total, auto-closes in 2s 9. Cart API errors surface user-visible error messages 10. Tapping "Send to Cart" on an already-sent tab is blocked |
| **Agent type** | Extension-UI |
| **Workstream** | C |
| **SPEC reference** | §3.5 Cart API Integration, §3.6 Data Flow, §5.4 Send to Cart Flow, §6 Error Handling |

---

### T-12 — Extension: TabList view (multiple tables/tabs)

| Field | Value |
|---|---|
| **Description** | Create `src/components/TabList.tsx` — list view of all open tabs across tables. Fetch from `GET /api/v1/tabs/open`. Each row shows: table name, item count, total amount, timer (how long tab has been open). Tap to switch active tab. "New Tab" button opens table selector. Wire into `modal.tsx` as initial view when no tab is selected. |
| **Files** | `extension/src/components/TabList.tsx` (create) |
| **Dependencies** | T-10 (TabBill + tab management must exist — TabList navigates to TabBill) |
| **Priority** | **P1** — important for multi-table stores, but single-table store can work without it |
| **Effort** | **M** — list rendering, navigation state, timer display. ~150 lines. |
| **Acceptance criteria** | 1. `TabList` renders all open tabs from `GET /api/v1/tabs/open` 2. Each row shows table name, item count, formatted total (€XX.XX), elapsed time 3. Tapping a tab navigates to TabBill view for that tab 4. "New Tab" button opens table selector dropdown 5. Empty state shows "No open tabs" 6. Tabs auto-refresh (poll or event) when another device adds items 7. Switching between tabs preserves each tab's state |
| **Agent type** | Extension-UI |
| **Workstream** | C |
| **SPEC reference** | §5.3 Modal — Tab List View |

---

### T-13 — Extension: Error handling (backend down, Cart API fail, retry logic)

| Field | Value |
|---|---|
| **Description** | Implement comprehensive error handling across the extension. Handle: (1) backend unreachable — show `s-banner` error, allow retry, show cached products if available (per SPEC §6), (2) Cart API individual item failure — show which item failed, skip it, continue with remaining items, (3) cart-not-empty warning before clear, (4) tab-already-sent prevention (disable button, show "Sent at HH:MM"), (5) network timeout on send-to-cart — retry with exponential backoff (3 attempts), if all fail offer "Save as draft order" fallback, (6) missing variant ID → fallback to addCustomSale. Implement these in `api/client.ts`, `hooks/useCartApi.ts`, and `components/SendToCart.tsx`. |
| **Files** | `extension/src/api/client.ts` (modify — retry logic), `extension/src/hooks/useCartApi.ts` (modify — per-item error handling), `extension/src/components/SendToCart.tsx` (modify — error banners), `extension/src/hooks/useProducts.ts` (modify — caching/fallback) |
| **Dependencies** | T-11 (Cart API integration must exist first to add error wrapping) |
| **Priority** | **P1** — essential for production reliability |
| **Effort** | **M** — touches 4 files with retry, fallback, and error UI patterns. ~200 lines. |
| **Acceptance criteria** | 1. Backend unreachable shows error banner with retry button 2. Cart API individual item failure shows which item failed, skips it 3. Non-empty cart shows confirmation before clear 4. Already-sent tab disables send button, shows sent timestamp 5. Network timeout triggers 3 retries with exponential backoff 6. After 3 failed retries, offers "Save as draft order" fallback 7. Missing variant ID silently falls back to addCustomSale (no user-facing error) 8. All errors surface user-readable messages via `s-banner` (not raw error objects) |
| **Agent type** | Extension-UI |
| **Workstream** | C |
| **SPEC reference** | §5.4 Send to Cart Flow, §6 Error Handling (full table) |

---

### T-14 — Extension: Loading states + success/confirmation flows

| Field | Value |
|---|---|
| **Description** | Add `s-spinner` loading states to: (1) initial product/tab data fetch, (2) send-to-cart in-progress, (3) tab item add/remove. Add confirmation modal before send-to-cart: "Send X items (€YY.YY) to POS cart?" with Cancel/Confirm. Add success animation: checkmark + "Items sent to cart! ✅" with auto-close after 2s. Add error state with retry. Implemented in `SendToCart.tsx` and wired into `modal.tsx`. |
| **Files** | `extension/src/components/SendToCart.tsx` (modify — add confirmation + success), `extension/src/modal.tsx` (modify — add loading states), `extension/src/styles/extension.css` (modify — add animations) |
| **Dependencies** | T-11 (send-to-cart flow must exist) |
| **Priority** | **P1** — UX polish, important for user confidence |
| **Effort** | **S** — confirmation modal, spinner, success animation. ~80 lines. |
| **Acceptance criteria** | 1. Tapping "Send to POS Cart" first shows confirmation modal with item count + total 2. Confirming shows `s-spinner` during Cart API calls 3. Success shows checkmark + message + auto-close after 2s 4. Error shows error details + retry button 5. Cancel on confirmation modal returns to tab view without changes 6. Loading states prevent double-taps (button disabled while loading) |
| **Agent type** | Extension-UI |
| **Workstream** | C |
| **SPEC reference** | §5.4 Send to Cart Flow |

---

### T-15 — Backend: Transaction history endpoint (`/api/v1/transactions`)

| Field | Value |
|---|---|
| **Description** | The existing `GET /api/v1/transactions` endpoint (app.py line 1283) already lists transactions but uses the old `_check_api_key()` pattern and returns legacy fields only. Refactor this endpoint to: (1) use the new `verify_api_key` dependency from T-05, (2) include new POS fields (`pos_order_id`, `pos_terminal_id`, `checkout_method`), (3) support filtering by `checkout_method` (pos_extension | draft_order), (4) ensure pagination works correctly for POS extension consumers. |
| **Files** | `app.py` (modify — update existing route) |
| **Dependencies** | T-04 (send-to-cart creates transactions with new fields), T-05 (auth middleware) |
| **Priority** | **P2** — useful for history view in extension, but not MVP-blocking |
| **Effort** | **S** — refactor existing endpoint, add new fields. ~50 lines. |
| **Acceptance criteria** | 1. `GET /api/v1/transactions` returns transactions including `pos_order_id`, `pos_terminal_id`, `checkout_method` 2. Filtering by `?checkout_method=pos_extension` returns only POS-originated transactions 3. Auth uses the same middleware as other `/api/v1/*` endpoints 4. No breaking changes to existing transaction endpoint consumers 5. Pagination (`page`, `per_page`) works correctly |
| **Agent type** | Backend |
| **Workstream** | A |
| **SPEC reference** | §3.4 New Endpoints (`GET /api/v1/transactions`) |

---

### T-16 — Testing: dev store setup guide + test case checklist

| Field | Value |
|---|---|
| **Description** | Create a development setup document: (1) Shopify dev store creation steps, (2) custom app install in Partners dashboard, (3) POS configuration (enable POS, add devices), (4) `shopify app dev` tunnel setup, (5) environment variable guide. Create a test case checklist matching SPEC §8.2 (T01-T10) with pass/fail columns, exact steps, and expected results. |
| **Files** | `docs/TESTING.md` or section in `docs/DEPLOYMENT.md` (future) — create as standalone `docs/TESTING.md` |
| **Dependencies** | T-11 (extension must be buildable to test — testing guide references built extension) |
| **Priority** | **P1** — needed for QA agent (Phase 3) to verify test cases |
| **Effort** | **S** — documentation, ~50 lines of markdown |
| **Acceptance criteria** | 1. Dev store setup covers: store creation, POS enable, app install, tunnel setup 2. Test checklist has 10 rows (T01-T10 from SPEC §8.2) with exact steps 3. Each test includes expected result (from SPEC §8.2) 4. Checklist has columns: Test ID, Scenario, Steps, Expected, Actual, Pass/Fail 5. Setup guide includes all required env vars and their sources |
| **Agent type** | Docs |
| **Workstream** | — |
| **SPEC reference** | §8.1 Dev Store Testing, §8.2 Test Cases, §8.3 E2E Flow, §9 Deployment |

---

## 3. Critical Path Analysis

The critical path is the **longest sequence of dependent tasks** that determines the minimum Phase 2 build time. There are three chains that converge.

### Chain A (Backend → Extension Core)
```
T-05 (S, 1h) ──┐
                ├──→ T-08 (S, 1.5h) ──→ T-10 (M, 4h) ──→ T-11 (L, 10h) ──→ T-13 (M, 4h) ──→ T-16 (S, 1h)
T-02 (S, 1h) ──┘
```
**Cumulative:** ~22.5 hours

### Chain B (DB → Tab CRUD → Extension)
```
T-01 (S, 1h) ──→ T-03 (M, 4h) ──→ T-04 (S, 1.5h) ──→ T-11 (L, 10h) ──→ T-13 (M, 4h) ──→ T-16 (S, 1h)
```
**Cumulative:** ~21.5 hours

### Chain C (Extension Scaffold)
```
T-06 (S, 1h) ──→ T-07 (S, 1h)
```
**Cumulative:** ~2 hours (parallel with Chains A/B)

### Result

The **critical path** is Chain A at **~22.5 hours**. T-11 (SendToCart Cart API integration) is the single most expensive task at ~10 hours. The scaffold (T-06 + T-07) is independent and can complete early. Task T-12 (TabList) and T-14 (Loading states) fork from T-10 and T-11 respectively and can run partially in parallel with T-11/T-13.

**Minimum Phase 2 build time:** ~22.5 hours of focused build effort (assuming 1 agent per workstream), or ~3 working days with overhead.

```
Timeline (hours):
0     2     4     6     8     10    12    14    16    18    20    22    24
├─────┤
T-01  T-03───┤                                                          (Chain B)
├─────┤       T-04──┐
├─────┤             │
T-05  ├──→T-08──→T-10──→T-11────────────────────→T-13──→T-16         (Chain A — CRITICAL)
├─────┤       │
T-02──┘       └──→T-09──┐  (parallel off T-08)
                        │
                        ├──→T-12──┐  (parallel off T-10)
                        │         │
                        └─────────┤
                                  └──→T-14──┐  (parallel off T-11)
                                            │
                                            └──── (merge at T-13)
├─────┤
T-06──→T-07                                                             (Chain C — independent)
                           ├────┤
                           T-15 (P2 — optional parallel)
```

---

## 4. Parallelization Matrix

### Allowed Parallel Execution

| Group | Tasks | Reason |
|---|---|---|
| **Group 1** (start of Phase 2) | T-01, T-05, T-06 | Touch different files: T-01→models.py+migrations/, T-05→app.py+config.py, T-06→extension/ |
| **Group 2** (after T-05) | T-02, T-07 | T-02→app.py (new route), T-07→extension/src/ |
| **Group 3** (after T-01 + T-05) | T-03, T-07 | T-03→app.py, T-07→extension/ |
| **Group 4** (after T-02 + T-05) | T-08, T-09 | T-08→api/client.ts+hooks, T-09→components/ — but T-09 depends on T-08, so sequential |
| **Group 5** (after T-03 + T-08) | T-10, T-12 | T-10→TabBill, T-12→TabList — same directory, can be done in parallel by separate Extension-UI agents if careful with imports |
| **Group 6** (after T-10 + T-04) | T-11, T-15 | T-11→extension/ (large), T-15→app.py (small) — completely independent |
| **Group 7** (after T-11) | T-13, T-14 | T-13→error handling, T-14→loading states — both modify overlapping components (SendToCart.tsx, modal.tsx), best done sequentially |

### Serialization Constraints (File Conflicts)

| Constraint | Reason | Workaround |
|---|---|---|
| **T-02, T-03, T-04, T-05, T-15 all touch app.py** | All add/modify routes in the same file | **Must be sequential.** Order: T-05 (middleware) → T-02 (read endpoints) → T-03 (tab CRUD) → T-04 (send-to-cart) → T-15 (transactions). An alternative is to split into `app_pos.py` importing from a shared router, but this would be a larger refactor than the benefit justifies. |
| **T-10, T-11, T-12, T-13, T-14 all touch extension/src/components/** | Shared component directory | T-10 (TabBill) can be parallel with T-12 (TabList). T-11 (SendToCart) is independent. T-13 and T-14 both modify SendToCart.tsx — must be sequential (T-14 after T-13, or merged into one pass). |
| **T-08 touches both api/ and hooks/** | Shared with T-09 (ProductGrid uses useProducts hook) | T-09 depends on T-08, so no conflict. T-10 depends on T-08's useTabs hook — also sequential. |

### Workstream Assignment Summary

```
Workstream A (Backend Agent)         Workstream B (Scaffold Agent)     Workstream C (Extension-UI Agent)
─────────────────────────────        ────────────────────────          ──────────────────────────────────
T-01 (models.py+migrations)  ──┐    T-06 (scaffold config) ──┐        (waits for A+B to produce endpoints)
                               │                              │
T-05 (app.py: middleware) ────┤│    T-07 (tile+modal shell)  │        T-08 (API client + hooks)
                               ││                              │        T-09 (CategoryBar + ProductGrid)
T-02 (app.py: products/cats)   ││                              │        T-10 (TabBill)
                               ││                              │        T-12 (TabList) [P1 — parallel with T-10]
T-03 (app.py: tabs CRUD) ────┤│                              │        T-11 (SendToCart + Cart API) [L]
                               ││                              │        T-13 (Error handling)
T-04 (app.py: send-to-cart)    ││                              │        T-14 (Loading states) [P1]
                               ││                              │        
T-15 (app.py: transactions)   ─┘                               │        T-16 (Testing doc)
```

**Key insight:** Workstream A must produce app.py additions in order (T-05→T-02→T-03→T-04→T-15) because they all touch the same file. Workstream B finishes quickly. Workstream C starts after T-05, T-02, and T-03 produce functioning endpoints.

---

## 5. Risk Register

| # | Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|---|
| **R1** | **Shopify POS Cart API — `addLineItem` uses variant price, ignores custom price.** If a product has a Shopify variant that costs €5.00 but the floor price is €3.85 (price override), calling `addLineItem(shopifyVariantId, qty)` will add it at €5.00, not €3.85. This is the core reason the existing app uses draft orders with custom line item prices. | **HIGH** — incorrect pricing in POS cart, customers charged wrong amounts | **Very High** — confirmed by prior research; this is a fundamental Cart API constraint | SPEC §3.5 handles this: use `addCustomSale(title, price, qty, taxable)` for all items with price overrides. For items without overrides, `addLineItem` is safe because the variant price matches. The `SendToCart` component (T-11) must check `priceOverride` on every item. Implementation must also handle the edge case where a product has no `shopify_variant_id` — fall back to `addCustomSale` (SPEC §6). |
| **R2** | **Shopify session token validation — no existing backend implementation.** The POS extension gets a Shopify session token (JWT) that the backend must verify. There is currently NO JWT verification code in `app.py`, `auth.py`, or `config.py`. The existing auth is session-cookie-based. Adding JWT verification requires the `SHOPIFY_SESSION_SECRET` env var and a PyJWT dependency. | **HIGH** — without token verification, any POS extension could impersonate any shop | **Medium** — standard pattern, well-documented | Add `pyjwt` (or `python-jose`) to requirements. Add `verify_shopify_token()` dependency in T-05 that validates the JWT signature using the app's client secret (stored in env var). The Shopify API documentation for session tokens provides the verification algorithm. SPEC §7.1 and §7.3 describe the auth chain but don't specify the JWT library — the build agent must choose one. |
| **R3** | **`clearCart()` may destroy in-progress POS checkout.** If a POS staff member has already built up a cart (e.g., walk-in customer items) and then opens Tab Tracker and taps "Send", calling `clearCart()` would wipe the existing items. This is a real workflow conflict. | **MEDIUM** — could cause lost sales if existing cart is discarded accidentally | **Medium** — common in multi-tasking POS environments | SPEC §6 requires: before clearing, show warning "Cart has existing items. Clear and replace? [Clear] [Cancel]". Cancel returns to tab view. Additionally, include a "Replace" vs "Append" option if Cart API allows (unlikely — Cart API doesn't support appending to non-empty cart well). The T-11 acceptance criteria cover this. |
| **R4** | **`addLineItem` variant ID mismatch — product may have no `shopify_variant_id`.** Products created locally in Tab Tracker (not synced from Shopify) won't have a `shopify_variant_id`. The existing `models.py` shows `shopify_variant_id` is nullable (line 69). Products can be added via the admin panel without ever syncing from Shopify. | **MEDIUM** — non-synced products can't use `addLineItem`, would fail silently | **High** — bakery likely has locally-managed products | SPEC §6 already specifies: "Shopify variant missing → Fall back to `addCustomSale` with product name + price". The `useCartApi` hook (T-11) must check for `shopifyVariantId` on every item before choosing `addLineItem` vs `addCustomSale`. This is covered in T-11 acceptance criteria. |
| **R5** | **Network access: extension can't reach backend from POS device.** The `shopify.extension.toml` has `network_access = true`, but the POS device (iPad on in-store WiFi) must be able to reach the VPS at `178.104.146.136:8095`. In-store WiFi may have firewall rules, or the VPS may not accept connections from the POS subnet. Additionally, Shopify POS extensions are served from an iframe on Shopify's CDN — the extension JS makes fetch calls to the backend, which must have correct CORS headers. | **HIGH** — no network = extension can't load products or tabs | **Medium** — depends on network config | Mitigation: (1) verify CORS on backend — FastAPI must have `CORSMiddleware` allowing the Shopify POS origin(s), (2) add `network_access: true` in `shopify.extension.toml` (already in SPEC §4.2), (3) test via `shopify app dev` tunnel before production, (4) document firewall rules needed for deployment. CORS is not currently configured in app.py (no `CORSMiddleware` import). T-05 should include adding CORS middleware. |
| **R6** | **Rate limiting not implemented.** SPEC §7.2 requires rate limiting on API endpoints. The existing app.py has NO rate limiting. Without it, a misbehaving extension (or attacker) could hammer the backend. | **LOW-MEDIUM** — operational stability | **Low** — single-shop pilot with limited POS devices | Add `slowapi` or similar to `app.py` in T-05. A simple 60 req/min per IP is sufficient for the pilot. De-prioritize if the build agent finds it complex — this is a P2 operational concern not blocking MVP. |

---

## 6. Acceptance Gates

### Gate A: Before Phase 3 (QA) can begin

All of the following must be true:

1. **All P0 tasks (T-01 through T-11) are complete** with acceptance criteria met. QA cannot test the extension without the full data flow (DB → backend → API client → UI → Cart API).

2. **T-16 (Testing doc) is written** — QA agent uses the test case checklist to verify SPEC §8.2 test cases T01-T10.

3. **Extension builds successfully**: `cd extension && npm run build` exits 0.

4. **Backend runs without errors**: `python3 app.py` starts and `/health` returns 200.

5. **DB migration applied**: `psql -U tabtracker -d tabtracker -f migrations/002_pos_extension.sql` succeeds. All new tables and columns are present.

6. **Existing web UI regression check**: Loading `/`, `/admin`, `/history` in browser returns HTML (not 500 errors). The HTMX tab operations (`/api/tabs/{id}/items`) still work. The draft order flow (`/api/tabs/{id}/send-to-shopify`) still works if called.

7. **P1 tasks may be incomplete** but must not break P0 flow. Specifically:
   - T-12 (TabList) — if incomplete, the extension can still work with single-table mode.
   - T-13 (Error handling) — if incomplete, basic error paths should at least not crash the app.
   - T-14 (Loading states) — if incomplete, extension works but has no spinners or success animations.

### Gate B: Before Phase 4 (Security) can begin

All of the following must be true:

1. **All P0 + P1 tasks are complete** (T-01 through T-14). Security must audit the full extension including error handling and Cart API integration.

2. **T-15 (Transactions) should be complete** — the transaction endpoint is used in the send-to-cart flow and must be secured.

3. **QA agent has passed** all SPEC §8.2 test cases (T01-T10) or documented known failures with root cause analysis.

4. **Code is on `feat/pos-extension` branch** with all changes committed (not pushed — orchestrator handles that).

5. **No hardcoded secrets** — extension `src/` must not contain API keys, tokens, or passwords (verified by grep `grep -r "shpat_\|sk_\|api_key\|API_KEY" extension/src/`).

6. **`.env.example` updated** with all new env vars (CHECKOUT_METHOD, SHOPIFY_SESSION_SECRET) — no real values.

7. **P2/P3 tasks** (e.g., T-15 enhancements, future features) may be deferred.

### Rationale

The gates ensure that each downstream phase has a stable, testable artifact. QA can't verify the send-to-cart flow if T-11 is incomplete. Security can't audit auth if T-05 (middleware) hasn't been built. The gates are concrete and falsifiable — no subjective "done enough" assessments.

---

## Appendix: File Conflict Map

| File | Touched By | Conflict? |
|---|---|---|
| `app.py` | T-02, T-03, T-04, T-05, T-15 | **YES** — all add/modify routes. Must serialize. |
| `models.py` | T-01 | No conflict (single touch). |
| `config.py` | T-05 | No conflict (single touch). |
| `migrations/002_pos_extension.sql` | T-01 | No conflict (new file). |
| `extension/shopify.extension.toml` | T-06 | No conflict (new file). |
| `extension/package.json` | T-06 | No conflict (new file). |
| `extension/src/index.tsx` | T-07 | No conflict (new file). |
| `extension/src/modal.tsx` | T-07, T-14 | **LOW** — T-14 adds loading states, can be merged. |
| `extension/src/api/client.ts` | T-08, T-13 | **LOW** — T-13 adds retry logic to existing client. Sequential recommended. |
| `extension/src/hooks/useProducts.ts` | T-08, T-13 | **LOW** — T-13 adds caching/fallback. Sequential. |
| `extension/src/hooks/useCartApi.ts` | T-11, T-13 | **LOW** — T-13 wraps Cart API calls in error handling. Sequential. |
| `extension/src/components/CategoryBar.tsx` | T-09 | No conflict. |
| `extension/src/components/ProductGrid.tsx` | T-09 | No conflict. |
| `extension/src/components/ProductCard.tsx` | T-09 | No conflict. |
| `extension/src/components/TabBill.tsx` | T-10 | No conflict. |
| `extension/src/components/TabList.tsx` | T-12 | No conflict (new file). |
| `extension/src/components/SendToCart.tsx` | T-11, T-13, T-14 | **YES** — all 3 tasks modify this file. Must sequence: T-11 (build) → T-13 (error wrap) → T-14 (loading states+animations). |
| `extension/src/types/index.ts` | T-06 | No conflict. |
| `extension/src/styles/extension.css` | T-07, T-14 | **LOW** — T-14 adds animation styles. Can be merged. |
| `shopify.py` | None | Unchanged (Cart API is client-side, draft order flow preserved). |
| `templates/floor.html` | None | Unchanged (must not break). |
| `templates/admin.html` | None | Unchanged. |
| `templates/history.html` | None | Unchanged. |

---

*End of PM Report — Phase 1 complete. Ready for Phase 2 (Build) execution.*
