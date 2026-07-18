# Tab Tracker POS Extension — API Reference

**Base URL:** `http://<server>:8095` (production: `https://api.example.com`)
**Schema:** All endpoints return JSON
**Auth:** `X-API-Key` header required on all `/api/v1/*` endpoints

---

## Table of Contents

1. [Authentication](#1-authentication)
2. [Products & Categories](#2-products--categories)
3. [Tables & Tabs](#3-tables--tabs)
4. [Transactions](#4-transactions)
5. [Cart API Contract (Extension-Side)](#5-cart-api-contract-extension-side)
6. [Rate Limiting](#6-rate-limiting)
7. [CORS Configuration](#7-cors-configuration)

---

## 1. Authentication

### X-API-Key Header

All `/api/v1/*` endpoints require the `X-API-Key` header. The value must match the `TAB_TRACKER_API_KEY` environment variable configured on the server.

**Source:** [`app.py:65-98`](../app.py) (`verify_api_key` dependency)

```bash
curl -H "X-API-Key: your-generated-api-key" http://localhost:8095/api/v1/products
```

**401 response (missing or invalid key):**

```json
{
  "detail": "Invalid or missing API key"
}
```

### Optional: X-Shop-Location Header

The `X-Shop-Location` header may be sent to specify the Shopify location ID. The backend resolves this to a `shop_id` for multi-shop support. If omitted, the first active shop is used.

### Shopify JWT Session Verification

**⚠️ Pilot-only note:** SPEC §7.2 mandates dual authentication (X-API-Key + Shopify session JWT). The `verify_api_key` dependency currently checks only the static API key. `SHOPIFY_SESSION_SECRET` is defined in [`config.py:36`](../config.py) but JWT verification is not yet implemented. See [Known Issues](README.md#known-issues--follow-up) (SEC-003).

---

## 2. Products & Categories

### `GET /api/v1/products`

Return all active products with category info and active price overrides.

**Auth:** `X-API-Key` header required
**Source:** [`app.py:1523-1561`](../app.py)

**Example request:**
```bash
curl -H "X-API-Key: your-generated-api-key" http://localhost:8095/api/v1/products
```

**Example 200 response:**
```json
[
  {
    "id": 1,
    "name": "Classic Alfajor",
    "slug": "classic-alfajor",
    "price": 3.85,
    "currency": "EUR",
    "category_id": 1,
    "category_name": "Alfajores",
    "shopify_variant_id": 4567890123,
    "shopify_product_id": 4567890123,
    "image_path": "/static/images/products/classic-alfajor.jpg",
    "override_price": 3.5,
    "is_active": true
  }
]
```

**Error responses:** `401` (missing/invalid API key)

---

### `GET /api/v1/categories`

Return all active categories ordered by sort order.

**Auth:** `X-API-Key` header required
**Source:** [`app.py:1564-1586`](../app.py)

**Example request:**
```bash
curl -H "X-API-Key: your-generated-api-key" http://localhost:8095/api/v1/categories
```

**Example 200 response:**
```json
[
  {
    "id": 1,
    "name": "Alfajores",
    "icon": "🍪",
    "sort_order": 1,
    "is_active": true
  }
]
```

**Error responses:** `401` (missing/invalid API key)

---

## 3. Tables & Tabs

### `GET /api/v1/tables`

Return all active tables for the current shop.

**Auth:** `X-API-Key` header required
**Source:** [`app.py:1591-1617`](../app.py)

**Example request:**
```bash
curl -H "X-API-Key: your-generated-api-key" http://localhost:8095/api/v1/tables
```

**Example 200 response:**
```json
[
  {
    "id": 1,
    "name": "Table 1",
    "seats": 4,
    "sort_order": 1,
    "is_active": true
  }
]
```

**Error responses:** `401` (missing/invalid API key)

---

### `GET /api/v1/tabs`

Get the open tab (with items) for a specific table.

**Query parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `table_id` | int | **Yes** | Table ID to look up |

**Auth:** `X-API-Key` header required
**Source:** [`app.py:1675-1723`](../app.py)

**Example request:**
```bash
curl -H "X-API-Key: your-generated-api-key" "http://localhost:8095/api/v1/tabs?table_id=1"
```

**Example 200 response (tab exists):**
```json
{
  "tab": {
    "id": 10,
    "table_id": 1,
    "status": "open",
    "guests": 1,
    "opened_at": "2026-07-19T10:30:00+00:00",
    "closed_at": null,
    "pos_cart_sent_at": null,
    "pos_terminal_id": "pos-terminal-01",
    "notes": null
  },
  "items": [
    {
      "id": 42,
      "product_id": 1,
      "product_name": "Classic Alfajor",
      "unit_price": 3.85,
      "quantity": 2,
      "added_at": "2026-07-19T10:35:00+00:00"
    }
  ],
  "total": 7.70
}
```

**Example 200 response (no open tab):**
```json
{
  "tab": null,
  "items": []
}
```

**Error responses:** `400` (no shop configured), `401` (invalid API key)

---

### `GET /api/v1/tabs/open`

Return all open tabs across all tables, with items and totals.

**Auth:** `X-API-Key` header required
**Source:** [`app.py:1622-1672`](../app.py)

**Example request:**
```bash
curl -H "X-API-Key: your-generated-api-key" http://localhost:8095/api/v1/tabs/open
```

**Example 200 response:**
```json
[
  {
    "id": 10,
    "table_id": 1,
    "table_name": "Table 1",
    "status": "open",
    "guests": 1,
    "item_count": 3,
    "total": 12.55,
    "opened_at": "2026-07-19T10:30:00+00:00",
    "notes": null,
    "items": [
      {
        "id": 42,
        "product_id": 1,
        "product_name": "Classic Alfajor",
        "unit_price": 3.85,
        "quantity": 2,
        "added_at": "2026-07-19T10:35:00+00:00"
      }
    ]
  }
]
```

**Error responses:** `401` (invalid API key)

---

### `POST /api/v1/tabs`

Open a new tab for a table. Creates a `pos_sessions` row tracking the terminal.

**Auth:** `X-API-Key` header required
**Source:** [`app.py:1727-1788`](../app.py)

**Request body schema** (Pydantic `OpenTabRequest`, `app.py:1503-1508`):

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `table_id` | int | **Yes** | — | Table to open the tab on |
| `pos_terminal_id` | str | No | `null` | POS terminal identifier |
| `staff_id` | str | No | `null` | Staff member identifier |
| `guests` | int | No | `1` | Number of guests |
| `notes` | str | No | `null` | Optional notes |

**Example request:**
```bash
curl -X POST http://localhost:8095/api/v1/tabs \
  -H "X-API-Key: your-generated-api-key" \
  -H "Content-Type: application/json" \
  -d '{"table_id": 1, "pos_terminal_id": "pos-terminal-01", "guests": 4}'
```

**Example 201 response:**
```json
{
  "id": 10,
  "table_id": 1,
  "status": "open",
  "guests": 4,
  "opened_at": "2026-07-19T10:30:00+00:00",
  "pos_session_id": 5
}
```

**Error responses:**
- `400` — No shop configured
- `401` — Invalid API key
- `404` — Table not found
- `409` — Table already has an open tab

---

### `POST /api/v1/tabs/{tab_id}/items`

Add an item (product) to an open tab. Merges with existing line items of the same product and price (increments quantity).

**Auth:** `X-API-Key` header required
**Source:** [`app.py:1791-1865`](../app.py)

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `tab_id` | int | Open tab ID |

**Request body schema** (Pydantic `AddItemRequest`, `app.py:1510-1511`):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `product_id` | int | **Yes** | Product to add |

> **Note:** The extension client may send `quantity` and `override_price` fields — these are silently stripped by Pydantic; the backend always adds quantity=1 and resolves override_price server-side from the `PriceOverride` table.

**Example request:**
```bash
curl -X POST http://localhost:8095/api/v1/tabs/10/items \
  -H "X-API-Key: your-generated-api-key" \
  -H "Content-Type: application/json" \
  -d '{"product_id": 1}'
```

**Example 201 response:**
```json
{
  "items": [
    {
      "id": 42,
      "product_id": 1,
      "product_name": "Classic Alfajor",
      "unit_price": 3.85,
      "quantity": 1,
      "added_at": "2026-07-19T10:35:00+00:00"
    }
  ],
  "total": 3.85
}
```

**Error responses:**
- `401` — Invalid API key
- `404` — Tab not found or not open / Product not found

---

### `DELETE /api/v1/tabs/{tab_id}/items/{item_id}`

Remove an item from a tab.

**Auth:** `X-API-Key` header required
**Source:** [`app.py:1868-1905`](../app.py)

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `tab_id` | int | Tab ID |
| `item_id` | int | TabItem ID to remove |

**Example request:**
```bash
curl -X DELETE http://localhost:8095/api/v1/tabs/10/items/42 \
  -H "X-API-Key: your-generated-api-key"
```

**Example 200 response:**
```json
{
  "items": [],
  "total": 0
}
```

**Error responses:**
- `401` — Invalid API key
- `404` — Item not found

---

### `PATCH /api/v1/tabs/{tab_id}/items/{item_id}`

Update item quantity. If quantity ≤ 0, the item is removed.

**Auth:** `X-API-Key` header required
**Source:** [`app.py:1908-1950`](../app.py)

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `tab_id` | int | Tab ID |
| `item_id` | int | TabItem ID |

**Request body schema** (Pydantic `UpdateItemQtyRequest`, `app.py:1513-1514`):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `quantity` | int | **Yes** | New quantity (≤ 0 removes item) |

**Example request:**
```bash
curl -X PATCH http://localhost:8095/api/v1/tabs/10/items/42 \
  -H "X-API-Key: your-generated-api-key" \
  -H "Content-Type: application/json" \
  -d '{"quantity": 3}'
```

**Example 200 response:**
```json
{
  "items": [
    {
      "id": 42,
      "product_id": 1,
      "product_name": "Classic Alfajor",
      "unit_price": 3.85,
      "quantity": 3
    }
  ],
  "total": 11.55
}
```

**Error responses:**
- `401` — Invalid API key
- `404` — Item not found

---

### `POST /api/v1/tabs/{tab_id}/close`

Close a tab (after POS checkout completes). Marks status as `closed` and records `closed_at`.

**Auth:** `X-API-Key` header required
**Source:** [`app.py:1953-1981`](../app.py)

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `tab_id` | int | Tab ID |

**Optional request body** (Pydantic `CloseTabRequest`, `app.py:1516-1518`):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `pos_terminal_id` | str | No | Terminal that closed the tab |
| `staff_id` | str | No | Staff ID |

**Example request:**
```bash
curl -X POST http://localhost:8095/api/v1/tabs/10/close \
  -H "X-API-Key: your-generated-api-key" \
  -H "Content-Type: application/json" \
  -d '{"pos_terminal_id": "pos-terminal-01"}'
```

**Example 200 response:**
```json
{
  "id": 10,
  "table_id": 1,
  "status": "closed",
  "closed_at": "2026-07-19T11:00:00+00:00"
}
```

**Error responses:**
- `400` — Tab already closed
- `401` — Invalid API key
- `404` — Tab not found

---

## 4. Transactions

### `POST /api/v1/tabs/{tab_id}/send-to-cart`

Record a tab as sent to the POS cart. Creates a `Transaction` record with a snapshot of all line items. Sets `tab.status = "sent"` and `tab.pos_cart_sent_at`.

> **⚠️ Important:** This endpoint records the transaction on the backend side. The actual Cart API calls (`clearCart`, `addLineItem`, `addCustomSale`) are performed **client-side** in the extension before calling this endpoint. If Cart API calls fail, this endpoint should NOT be called (no phantom transactions).

**Auth:** `X-API-Key` header required
**Source:** [`app.py:1991-2123`](../app.py)

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `tab_id` | int | Open tab ID |

**Optional request body** (Pydantic `SendToCartRequest`, `app.py:1986-1988`):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `pos_terminal_id` | str | No | Terminal ID for the transaction |
| `staff_id` | str | No | Staff ID |

**Example request:**
```bash
curl -X POST http://localhost:8095/api/v1/tabs/10/send-to-cart \
  -H "X-API-Key: your-generated-api-key" \
  -H "Content-Type: application/json" \
  -d '{"pos_terminal_id": "pos-terminal-01"}'
```

**Example 200 response:**
```json
{
  "transaction_id": 5,
  "tab_id": 10,
  "status": "sent",
  "total": 7.70,
  "item_count": 2
}
```

**Error responses:**
- `400` — Tab already sent / Tab is closed / Cannot send empty tab
- `401` — Invalid API key
- `404` — Tab not found

---

### `GET /api/v1/transactions`

List transaction records with optional filtering.

**Auth:** `X-API-Key` header required
**Source:** [`app.py:1332-1413`](../app.py)

**Query parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `page` | int (≥1) | No | Page number (default: 1) |
| `per_page` | int (1–500) | No | Items per page (default: 50) |
| `from_date` | str (YYYY-MM-DD) | No | Filter: sent_at ≥ date |
| `to_date` | str (YYYY-MM-DD) | No | Filter: sent_at ≤ date |
| `status` | str | No | Filter by shopify_status |
| `table_id` | int | No | Filter by table ID |
| `checkout_method` | str | No | Filter: `pos_extension` or `draft_order` |

**Example request:**
```bash
curl -H "X-API-Key: your-generated-api-key" \
  "http://localhost:8095/api/v1/transactions?page=1&per_page=10&checkout_method=pos_extension"
```

**Example 200 response:**
```json
{
  "transactions": [
    {
      "id": 5,
      "table": "Table 1",
      "shop": "Amsterdam Baking Company",
      "cashier": "Admin",
      "guests": 4,
      "total": 7.70,
      "currency": "EUR",
      "item_count": 2,
      "status": "sent",
      "shopify_draft_order_id": null,
      "pos_order_id": null,
      "pos_terminal_id": "pos-terminal-01",
      "checkout_method": "pos_extension",
      "opened_at": "2026-07-19T10:30:00+00:00",
      "sent_at": "2026-07-19T10:45:00+00:00",
      "completed_at": null,
      "items": [
        {
          "product_name": "Classic Alfajor",
          "checkout_name": "Classic Alfajor",
          "flavor": null,
          "unit_price": 3.85,
          "quantity": 2,
          "line_total": 7.70
        }
      ]
    }
  ],
  "page": 1,
  "per_page": 10,
  "total": 1,
  "total_pages": 1
}
```

**Error responses:** `401` (invalid API key)

---

### `GET /api/v1/transactions/{tx_id}`

Get a single transaction by ID, with line items.

**Auth:** `X-API-Key` header required
**Source:** [`app.py:1285-1329`](../app.py)

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `tx_id` | int | Transaction ID |

**Example request:**
```bash
curl -H "X-API-Key: your-generated-api-key" http://localhost:8095/api/v1/transactions/5
```

**Example 200 response:**
```json
{
  "id": 5,
  "table": "Table 1",
  "shop": "Amsterdam Baking Company",
  "cashier": "Admin",
  "guests": 4,
  "total": 7.70,
  "currency": "EUR",
  "item_count": 2,
  "status": "sent",
  "shopify_draft_order_id": null,
  "pos_order_id": null,
  "pos_terminal_id": "pos-terminal-01",
  "checkout_method": "pos_extension",
  "opened_at": "2026-07-19T10:30:00+00:00",
  "sent_at": "2026-07-19T10:45:00+00:00",
  "completed_at": null,
  "items": [
    {
      "product_name": "Classic Alfajor",
      "checkout_name": "Classic Alfajor",
      "flavor": null,
      "unit_price": 3.85,
      "quantity": 2,
      "line_total": 7.70,
      "shopify_variant_id": 4567890123
    }
  ]
}
```

**Error responses:**
- `401` — Invalid API key
- `404` — Transaction not found

---

## 5. Cart API Contract (Extension-Side)

The extension uses the Shopify POS Cart API (accessed via `api.cart` from the POS extension runtime context) to push items into the native POS cart before recording the transaction on the backend.

**Source:** [`extension/src/hooks/useCartApi.ts`](../extension/src/hooks/useCartApi.ts)

### Methods Used

| Method | Signature | When Used |
|--------|-----------|-----------|
| `clearCart()` | `() => Promise<void>` | First step of every send-to-cart flow. Clears any existing items in the POS cart. |
| `addLineItem` | `(variantId: number, quantity: number) => Promise<string>` | Used when the item has a valid `shopify_variant_id` AND no price override (or override_price equals unit_price). Passes the Shopify variant ID directly. |
| `addCustomSale` | `(sale: { title: string, price: string, quantity: number, taxable: boolean }) => Promise<string>` | Used when the item has a price override (override_price differs from unit_price) OR no `shopify_variant_id`. Creates a custom sale line in the cart. |

### Decision Rule (from `useCartApi.ts:78-98`)

```
if (item.shopify_variant_id != null && (item.override_price == null || item.override_price === item.unit_price))
  → cartApi.addLineItem(item.shopify_variant_id, item.quantity)
else
  → cartApi.addCustomSale({ title: item.product_name, price: displayPrice, quantity: item.quantity, taxable: true })
```

Where `displayPrice` = `item.override_price` if present and different, otherwise `item.unit_price`.

### Send-to-Cart Flow (from `Modal.tsx:255-296`)

1. **Get Cart API handle** from POS extension context: `apiHook.cart`
2. **Call** `sendItemsToCart(cartApi, activeTab.items)` which:
   - Calls `clearCart()`
   - Iterates items, calling `addLineItem` or `addCustomSale` per the decision rule
3. **If all items fail** (zero succeeded) → show error, **do NOT call backend**
4. **If at least some items succeeded** → call `POST /api/v1/tabs/{id}/send-to-cart` to persist the transaction record
5. Show success banner, auto-close modal after 2.5 seconds

### Cart API Handle Interface

```typescript
interface CartApiHandle {
  clearCart: () => Promise<void>;
  addLineItem: (variantId: number, quantity: number) => Promise<string>;
  addCustomSale: (sale: {
    title: string;
    price: string;
    quantity: number;
    taxable: boolean;
  }) => Promise<string>;
}
```

---

## 6. Rate Limiting

**⚠️ Currently not implemented.** No rate limiting middleware is applied to any endpoint. This is tracked as finding **SEC-007** in the [Security Audit Report](SECURITY_REPORT.md).

Planned limits (per SEC-007 recommendation):
- Read endpoints (`GET /api/v1/*`): 120 req/min per IP
- Write endpoints (`POST/PATCH/DELETE /api/v1/*`): 30 req/min per IP
- `POST /api/v1/tabs/{id}/send-to-cart`: 5 req/min per IP (critical financial operation)

---

## 7. CORS Configuration

The `POS_EXTENSION_ORIGIN` environment variable controls CORS behavior (source: [`config.py:34`](../config.py), [`app.py:35-41`](../app.py)):

| `POS_EXTENSION_ORIGIN` value | `allow_origins` | `allow_credentials` |
|------------------------------|-----------------|---------------------|
| `*` (default, pilot) | `["*"]` | `true` (⚠️ violates Fetch spec — browser may reject) |
| Specific URL (e.g., `https://admin.shopify.com`) | `["https://admin.shopify.com"]` | `true` (correct) |

**⚠️ Production note:** Lock down `POS_EXTENSION_ORIGIN` to the specific Shopify store domain before production deployment. The default `*` is acceptable for pilot but violates HTTP CORS spec when `allow_credentials=true`.

---

**Full source:** [`app.py`](../app.py) (2132 lines, all `/api/v1/*` endpoints at lines 1494–2123)
**Extension client:** [`extension/src/api/client.ts`](../extension/src/api/client.ts)
**Extension types:** [`extension/src/types/index.ts`](../extension/src/types/index.ts)
