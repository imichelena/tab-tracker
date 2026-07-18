# Tab Tracker → Shopify POS Extension — Build Specification

**Project:** Port the Tab Tracker web app into a native Shopify POS UI extension
**Repo:** `imichelena/tab-tracker`
**Branch:** `feat/pos-extension`
**Date:** 2026-07-18

---

## 1. Problem Statement

The bakery owner uses Shopify POS for checkout at the physical store. Shopify POS is excellent for payment processing, receipt printing, and inventory management, but it lacks:

- **Table tab tracking** — open a running tab per table, add items over time, send to checkout when ready
- **Quick product selection** — a customizable grid of products organized by category, optimized for speed
- **Price overrides** — display one price on the floor (e.g. €3.85 for a single alfajor) but checkout with a different Shopify variant

The current workaround creates Shopify **draft orders** from the tab tracker, but draft orders are invisible in Shopify POS, requiring a buggy third-party app to locate and complete them. This defeats the purpose.

## 2. Solution

Build a **Shopify POS UI extension** that embeds the tab tracker directly into the POS interface. Items built up in a tab are pushed **directly into the POS cart** via the Cart API — no draft orders, no third-party apps, native checkout.

```
┌─────────────────────────────────────────────────────┐
│                  Shopify POS App                     │
│                                                      │
│  ┌─────────────┐   ┌──────────────────────────────┐ │
│  │  POS Home    │   │  Tab Tracker Modal           │ │
│  │  Smart Grid  │   │  (pos.home.modal.render)     │ │
│  │              │   │                              │ │
│  │ ┌──────────┐ │   │  Category pills              │ │
│  │ │Tab Track ││──→│  Product grid (filtered)      │ │
│  │ │   er     ││   │  Tab bill (running total)     │ │
│  │ └──────────┘ │   │  [Send to POS Cart]          │ │
│  │              │   └──────────┬───────────────────┘ │
│  │  Regular POS  │              │ Cart API            │
│  │  functions    │              ▼                     │
│  │              │   ┌──────────────────────────────┐ │
│  │              │   │  POS Cart (native)            │ │
│  │              │   │  - Line items from tab        │ │
│  │              │   │  - Discounts applied          │ │
│  │              │   │  - Customer attached          │ │
│  │              │   │  [Charge] → native checkout   │ │
│  └─────────────┘   └──────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
         │ API calls (HTTPS)
         ▼
┌─────────────────────────────────────────────────────┐
│              Backend (FastAPI on VPS)                 │
│  - Product catalog + categories                      │
│  - Price override rules                              │
│  - Tab state (open tabs, tab items)                  │
│  - Transaction records (completed tabs)              │
│  - Shopify product sync                              │
│  - PostgreSQL (tab_tracker schema)                   │
│  - Analytics (analytics schema)                      │
└─────────────────────────────────────────────────────┘
```

## 3. Architecture

### 3.1 Components

| Component | Technology | Location |
|---|---|---|
| **POS Extension** | React/Preact + Shopify POS UI SDK | `extension/` directory in repo |
| **Backend API** | FastAPI (existing) + new endpoints | VPS: `178.104.146.136:8095` |
| **Database** | PostgreSQL (existing) | VPS: `tabtracker` DB |
| **Shopify App** | Custom (unlisted), Dev Dashboard | Shopify Partners |
| **Tunnel** | Tailscale → Caddy reverse proxy | For development/dev store testing |

### 3.2 POS Extension Structure

```
extension/
├── shopify.extension.toml      # Extension config (targets, capabilities)
├── package.json
├── tsconfig.json
├── vite.config.ts
├── src/
│   ├── index.tsx               # Entry point — pos.home.tile.render
│   ├── modal.tsx               # Full-screen modal — pos.home.modal.render
│   ├── components/
│   │   ├── CategoryBar.tsx     # Category filter pills
│   │   ├── ProductGrid.tsx     # Product selection grid
│   │   ├── ProductCard.tsx     # Individual product tile
│   │   ├── TabBill.tsx         # Running bill / ordered items
│   │   ├── TabList.tsx         # List of open tabs per table
│   │   └── SendToCart.tsx      # "Send to POS Cart" confirmation + action
│   ├── hooks/
│   │   ├── useProducts.ts      # Fetch products from backend
│   │   ├── useTabs.ts          # Tab CRUD via backend API
│   │   └── useCartApi.ts       # Shopify POS Cart API wrapper
│   ├── api/
│   │   └── client.ts           # Backend API client (fetch with auth)
│   ├── types/
│   │   └── index.ts            # TypeScript types (Product, Category, Tab, etc.)
│   └── styles/
│       └── extension.css       # Custom styles (within Shopify component limits)
└── README.md
```

### 3.3 Extension Targets (shopify.extension.toml)

```toml
[[extensions]]
type = "pos_ui_extension"
name = "Tab Tracker"

[[extensions.targets]]
target = "pos.home.tile.render"
module = "./src/index.tsx"

[[extensions.targets]]
target = "pos.home.modal.render"
module = "./src/modal.tsx"

[extensions.capabilities]
network_access = true
```

### 3.4 Backend API Changes

The backend stays FastAPI + PostgreSQL. We add new API endpoints specifically for the POS extension (authenticated via API key + Shopify session token):

#### New Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/products` | All active products with categories and price overrides |
| `GET` | `/api/v1/categories` | All active categories ordered by sort_order |
| `GET` | `/api/v1/tables` | All active tables for current shop |
| `GET` | `/api/v1/tabs?table_id=N` | Open tab + items for a table |
| `POST` | `/api/v1/tabs` | Open new tab for a table |
| `POST` | `/api/v1/tabs/{tab_id}/items` | Add item to tab |
| `DELETE` | `/api/v1/tabs/{tab_id}/items/{item_id}` | Remove item from tab |
| `PATCH` | `/api/v1/tabs/{tab_id}/items/{item_id}` | Update item quantity |
| `POST` | `/api/v1/tabs/{tab_id}/send-to-cart` | Mark tab as "sent", create transaction record |
| `GET` | `/api/v1/tabs/open` | All open tabs (for tab list view) |
| `POST` | `/api/v1/tabs/{tab_id}/close` | Close tab after POS checkout completes |
| `GET` | `/api/v1/transactions` | Transaction history (paginated) |

#### Authentication

The POS extension authenticates to the backend via:
1. **API key** — passed as `X-API-Key` header (same pattern as existing analytics API)
2. **Shop location ID** — passed as `X-Shop-Location` header, resolves to internal `shop_id`

The backend identifies which shop/location the POS terminal belongs to and scopes all queries accordingly.

### 3.5 Cart API Integration

When the user taps "Send to POS Cart" in the tab tracker modal:

```typescript
async function sendToCart(tab: Tab, items: TabItem[]) {
  // 1. Clear current cart (optional — or warn if cart not empty)
  await shopify.cart.clearCart();

  // 2. Add each line item
  for (const item of items) {
    if (item.priceOverride) {
      // Custom price — use addCustomSale
      await shopify.cart.addCustomSale({
        title: item.checkoutName || item.productName,
        price: item.unitPrice,
        quantity: item.quantity,
        taxable: true,
      });
    } else {
      // Standard product — use addLineItem with variantId
      await shopify.cart.addLineItem(item.shopifyVariantId, item.quantity);
    }
  }

  // 3. Apply cart-level discount if any
  // (e.g. rounding, staff discount)

  // 4. Attach customer if known
  // await shopify.cart.setCustomer(customer);

  // 5. Record transaction in backend
  await api.post(`/tabs/${tab.id}/send-to-cart`);
}
```

### 3.6 Data Flow — "Send to POS Cart"

```
Tab Tracker Modal          Shopify POS Cart API           Backend
       │                          │                         │
       │  User taps "Send"        │                         │
       ├─────────────────────────→│                         │
       │  clearCart()             │                         │
       │←─────────────────────────┤                         │
       │  addLineItem(variant,qty)│                         │
       ├─────────────────────────→│                         │
       │  addCustomSale(...)      │                         │
       ├─────────────────────────→│                         │
       │  applyCartDiscount(...)  │                         │
       ├─────────────────────────→│                         │
       │  setCustomer(...)        │                         │
       ├─────────────────────────→│                         │
       │  ✅ Cart populated        │                         │
       │←─────────────────────────┤                         │
       │                          │                         │
       │  POST /tabs/{id}/send-to-cart ─────────────────────→│
       │                          │    Create Transaction    │
       │                          │    Mark tab status=sent  │
       │←─────────────────────────────────────────────────────┤
       │                          │                         │
       │  Modal closes            │                         │
       │  User taps "Charge"      │                         │
       │  in POS (native checkout)│                         │
       │─────────────────────────→│                         │
       │  Payment, receipt, done  │                         │
       │                          │  (Webhook or manual)    │
       │                          │  POST /tabs/{id}/close ─→│
```

### 3.7 Database Changes

#### New: `pos_sessions` table

Tracks which POS terminal opened which tab, for audit and multi-terminal support.

```sql
CREATE TABLE tab_tracker.pos_sessions (
    id SERIAL PRIMARY KEY,
    shop_id INTEGER REFERENCES tab_tracker.shops(id),
    pos_terminal_id VARCHAR(100),     -- Shopify device ID
    staff_id VARCHAR(100),            -- Shopify staff ID
    opened_tab_ids INTEGER[],          -- Array of currently open tab IDs
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
```

#### Modified: `tabs` table

Add column for POS cart reference:

```sql
ALTER TABLE tab_tracker.tabs
  ADD COLUMN IF NOT EXISTS pos_cart_sent_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS pos_terminal_id VARCHAR(100);
```

#### Modified: `transactions` table

The `shopify_draft_order_id` column becomes optional. Replace with POS order reference:

```sql
ALTER TABLE tab_tracker.transactions
  ADD COLUMN IF NOT EXISTS pos_order_id VARCHAR(100),     -- Shopify order ID from POS checkout
  ADD COLUMN IF NOT EXISTS pos_terminal_id VARCHAR(100),
  ADD COLUMN IF NOT EXISTS checkout_method VARCHAR(20) DEFAULT 'pos_extension';  -- pos_extension | draft_order (legacy)
```

### 3.8 Backward Compatibility

The existing web UI (floor.html) continues to work for:
- Admin panel (product management, categories, price rules, sync)
- Transaction history
- Analytics dashboard

The draft order flow is preserved as a fallback (config flag `CHECKOUT_METHOD=pos_extension|draft_order`).

---

## 4. Shopify App Configuration

### 4.1 App Setup

| Setting | Value |
|---|---|
| App type | Custom (unlisted) |
| Partner account | Ignacio's Shopify Partners |
| Embedded | Yes (POS UI extension) |
| Scopes | `read_products`, `write_draft_orders` (legacy fallback), `read_orders` |
| POS permissions | Cart access, customer access, product access |
| Distribution | Custom install link (not App Store) |

### 4.2 POS Extension Capabilities

| Capability | Required |
|---|---|
| `network_access` | Yes — calls backend API |
| `pos.cart.api` | Yes — addLineItem, addCustomSale, clearCart, applyCartDiscount, setCustomer |
| `pos.customer.api` | Yes — read/set customer |
| `pos.device.api` | Optional — device ID for terminal tracking |
| `pos.storage.api` | Optional — cache product list locally |
| `pos.navigation.api` | Yes — close modal after send |

---

## 5. UI/UX Design

### 5.1 POS Home Tile

A clickable tile on the POS smart grid:
- Icon: 🍞 or custom
- Title: "Tab Tracker"
- Subtitle: "X open tabs" (if any)

### 5.2 Modal — Main View

Two-panel layout (same concept as current web app):

**Left panel (60%): Product selection**
- Category pills at top (horizontal scroll)
- Product grid (3-4 columns, scrollable)
- Each product card: image, name, price, tap to add

**Right panel (40%): Tab + bill**
- Table selector (dropdown or list)
- Current tab items (scrollable):
  - Product name, qty, unit price, line total
  - Swipe/tap to remove
  - Tap qty to adjust
- Running total
- Notes field
- "Send to POS Cart" button (large, sticky bottom)

### 5.3 Modal — Tab List View

If multiple tables:
- List of open tabs with table name, item count, total
- Tap to open/switch
- "New Tab" button → table selector

### 5.4 Send to Cart Flow

1. User taps "Send to POS Cart"
2. Confirmation modal: "Send X items (€YY.YY) to POS cart?"
3. Loading state while Cart API calls execute
4. Success: "Items sent to cart! ✅ Tap Charge to complete payment."
5. Modal auto-closes after 2s or user taps "Close"
6. Tab status → "sent", transaction record created

### 5.5 Component Constraints

Shopify POS UI extensions use Shopify's web component library (not arbitrary HTML). Available components:

| Component | Usage |
|---|---|
| `s-tile` | Home screen tile |
| `s-modal` | Full-screen modal container |
| `s-button` | Buttons |
| `s-list` | Product/tab item lists |
| `s-card` | Product cards |
| `s-text-field` | Notes, search |
| `s-select` | Table selector, category filter |
| `s-badge` | Category pills, status badges |
| `s-icon` | Icons |
| `s-spinner` | Loading states |
| `s-banner` | Success/error messages |

---

## 6. Error Handling

| Scenario | Behavior |
|---|---|
| Backend unreachable | Show error banner, allow retry. Cached products from last successful fetch if `pos.storage.api` available. |
| Cart API addLineItem fails | Show error, skip item, continue with remaining. Report which items failed. |
| Cart not empty on send | Warn user: "Cart has existing items. Clear and replace? [Clear] [Cancel]" |
| Tab already sent | Prevent double-send: disable button, show "Sent at HH:MM" |
| Shopify variant missing | Fall back to `addCustomSale` with product name + price |
| Network timeout on send | Retry with exponential backoff (3 attempts). If all fail, offer "Save as draft order" fallback. |

---

## 7. Security

### 7.1 Authentication Chain

```
Shopify POS Extension
  ↓ (Shopify session token JWT)
Backend API
  ↓ (API key validation + Shopify token verification)
PostgreSQL
```

### 7.2 Requirements

- Backend API endpoints (`/api/v1/*`) require `X-API-Key` header
- POS extension receives Shopify session token — backend verifies JWT signature using app secret
- All API calls over HTTPS (Caddy reverse proxy with Let's Encrypt)
- No secrets in extension code — all stored server-side
- Rate limiting on API endpoints
- Input validation on all POST/PATCH/DELETE

### 7.3 Secrets Management

| Secret | Storage |
|---|---|
| Shopify client ID / secret | Environment variables on VPS (`/opt/tab-tracker/.env`) |
| API key (for extension) | Shopify app metafield (injected at runtime) |
| Database credentials | Environment variables |
| Session secret | Environment variable |

---

## 8. Testing Strategy

### 8.1 Dev Store Testing

1. Create a Shopify development store with POS enabled
2. Install the custom app
3. Run Shopify CLI: `shopify app dev` → tunnels to local backend
4. Test on Shopify POS on an iPad/iPhone connected to dev store

### 8.2 Test Cases

| ID | Scenario | Expected |
|---|---|---|
| T01 | Open tab, add 3 items, send to cart | Cart shows 3 items with correct prices |
| T02 | Add item with price override | Cart shows custom sale with override price |
| T03 | Send to cart when cart not empty | Warning shown, user confirms clear |
| T04 | Close tab after checkout | Tab status = closed, transaction recorded |
| T05 | Backend down during tab operations | Error banner, cached products shown |
| T06 | Multiple tables with simultaneous tabs | Each tab independent, correct items per table |
| T07 | Product with no Shopify variant ID | addCustomSale fallback works |
| T08 | Add same product twice (qty increment) | Single line item, quantity = 2 |
| T09 | Remove item from tab | Item removed, total recalculated |
| T10 | Session timeout mid-tab | Tab state persisted server-side, recoverable |

### 8.3 E2E Flow (Manual)

1. Open POS app on device
2. Tap "Tab Tracker" tile
3. Select table
4. Add 2 coffees + 1 croissant
5. Tap "Send to POS Cart"
6. Verify cart in POS shows 3 items
7. Tap "Charge", process payment
8. Reopen Tab Tracker — tab shows "closed"

---

## 9. Deployment

### 9.1 Backend (VPS)

No infrastructure changes needed — existing FastAPI service on `178.104.146.136:8095` gets new `/api/v1/*` endpoints. Deployed via:

```bash
# Pull latest
cd /opt/tab-tracker && git pull origin feat/pos-extension

# Restart service
systemctl restart tab-tracker
```

### 9.2 POS Extension

```bash
# Build and deploy via Shopify CLI
cd extension/
shopify app deploy
```

Extension is served from Shopify's CDN — no VPS hosting needed for the extension itself.

### 9.3 Database Migration

```bash
psql -U tabtracker -d tabtracker -f migrations/002_pos_extension.sql
```

---

## 10. Migration Plan (Legacy → POS Extension)

| Phase | Action | Risk |
|---|---|---|
| 1 | Deploy backend with new API endpoints (backward compatible) | None — existing web UI still works |
| 2 | Install POS extension on dev store, test E2E | None — dev store only |
| 3 | Deploy to production Shopify store, install on one POS device | LOW — single device pilot |
| 4 | Owner uses POS extension for 1 day alongside existing flow | Feedback loop |
| 5 | Remove draft order code path (set `CHECKOUT_METHOD=pos_extension`) | Requires confidence from phase 4 |
| 6 | Optional: deprecate floor.html web UI if POS extension covers all needs | Only if owner requests |

---

## 11. Scope — What's IN vs OUT

### IN scope

- POS UI extension (tile + modal)
- Backend API endpoints for extension
- Cart API integration (addLineItem, addCustomSale, clearCart, applyCartDiscount, setCustomer)
- Tab/table state management via backend
- Transaction recording
- Price override support in cart flow
- Multi-table/multi-tab support
- Error handling + fallback to draft order

### OUT of scope (for this build)

- Analytics dashboard changes (already built separately)
- Customer-facing display screens
- Kitchen/printer integration
- Offline mode (POS extensions require network)
- Multiple shop/location support in POS extension (single shop pilot first)
- App Store publication (custom app only)
