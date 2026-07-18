# Tab Tracker — Shopify POS UI Extension

A Shopify POS UI extension that embeds table tab management directly into the POS
interface. Open tabs per table, add products by category, and send completed orders
to the native POS cart.

## Targets

| Target | Module | Description |
|---|---|---|
| `pos.home.tile.render` | `src/index.tsx` | Home screen tile — entry point |
| `pos.home.modal.render` | `src/Modal.tsx` | Full-screen tab management modal |

## Stack

- **Runtime:** Shopify POS UI Extension (sandboxed iframe)
- **UI:** React + `@shopify/ui-extensions-react` (Shopify web components)
- **Build:** Vite + TypeScript (strict mode)
- **Cart:** Shopify POS Cart API (`addLineItem`, `addCustomSale`, `clearCart`, etc.)
- **Backend:** FastAPI (external VPS) via network requests

## Development

```bash
# Install dependencies
npm install

# Start dev server + tunnel
shopify app dev

# Type-check
npm run check

# Production build
npm run build
```

## Configuration

All secrets (API keys, shop domain) are provided at runtime via Shopify app
metafields / extension settings — **never hardcoded**.

See `docs/` at the repo root for full spec, build plan, and deployment guide.
