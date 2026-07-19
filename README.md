# Tab Tracker

Tablet-optimized restaurant table tab tracking system for Amsterdam Baking Company,
now with a **Shopify POS UI Extension** that pushes items directly into the native POS cart.
Tracks open tabs per table, facilitates fast product selection by category, and hands off the
bill to Shopify checkout — either via the legacy web UI (draft orders) or the new POS extension
(Cart API, no third-party apps required).

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    Shopify POS Device                             │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │              Tab Tracker Extension Sandbox                │    │
│  │  (pos.home.tile.render tile → opens pos.home.modal.render)│    │
│  │                                                           │    │
│  │  ┌─────────────────┐  ┌──────────────────────────────┐   │    │
│  │  │  Product Grid    │  │  Tab Bill (running total)    │   │    │
│  │  │  (by category)   │  │  +/− qty, remove items       │   │    │
│  │  └────────┬────────┘  └──────────────┬───────────────┘   │    │
│  │           │                           │                   │    │
│  │           ▼                           ▼                   │    │
│  │  ┌──────────────────────────────────────────────────┐     │    │
│  │  │  [Send to POS Cart]                              │     │    │
│  │  │  1. clearCart() → addLineItem()/addCustomSale()  │     │    │
│  │  │  2. POST /api/v1/tabs/{id}/send-to-cart          │     │    │
│  │  └────────────────────┬─────────────────────────────┘     │    │
│  │                        │ Cart API (in-process)            │    │
│  └────────────────────────┼──────────────────────────────────┘    │
│                           │ HTTPS + X-API-Key                     │
└───────────────────────────┼──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│              Backend VPS (FastAPI on :8095)                       │
│  - Products & Categories (with price overrides)                   │
│  - Tables & Tab CRUD (open, add items, close)                     │
│  - Transaction records (pos_extension or draft_order)             │
│  - Shopify product sync                                           │
│  - X-API-Key auth (Shopify JWT pending — see Known Issues)       │
│  - CORS middleware (POS_EXTENSION_ORIGIN)                         │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│              PostgreSQL 'tabtracker' (schema tab_tracker)         │
│  - shops, tables, categories, products, price_overrides           │
│  - tabs, tab_items, transactions, transaction_items               │
│  - pos_sessions (NEW — terminal + staff tracking)                 │
│  - users, sync_logs, analytics tables                             │
└──────────────────────────────────────────────────────────────────┘
```

## Two Modes

| Mode | Description | Access |
|------|-------------|--------|
| **POS Extension** (primary, NEW) | Shopify POS UI extension — tile on the POS home screen opens a full tab-management modal. Items are pushed directly into the POS cart via Cart API (clearCart → addLineItem/addCustomSale). No draft orders, no third-party apps. Native Shopify checkout. | Shopify POS device with extension installed |
| **Web UI** (admin/floor, legacy) | Browser-based interface optimized for 10" tablets. Floor view with category grid, bill panel, table selector. Admin panel for product/category management and Shopify sync. Uses draft orders for checkout. | http://<server>:8095, login with admin/tab123 or cashier/tab123 |

## Stack

- **FastAPI** + **Jinja2** + **htmx**
- **PostgreSQL** (own schema `tab_tracker` — migration-ready)
- **Shopify Admin API** (draft orders, product sync)
- Target: 10" tablet (iPad), touch-optimized

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create database
sudo -u postgres psql -c "CREATE USER tabtracker WITH PASSWORD 'tabtracker';"
sudo -u postgres psql -c "CREATE DATABASE tabtracker OWNER tabtracker;"

# Initialize schema + seed data
python init_db.py

# Run
uvicorn app:app --host 0.0.0.0 --port 8095
```

## Configuration

Copy `.env.example` to `.env` and fill in Shopify credentials when ready.

## Default Users

| User | Password | Role |
|------|----------|------|
| admin | tab123 | Admin (products, prices, tables, sync) |
| cashier | tab123 | Cashier (tabs only) |

## Layout

- **Top bar** — table selector (always visible), table status + running totals
- **Left sidebar** — collapsible product categories with images + search
- **Right panel** — active tab bill with qty controls + "Send to Shopify" button
- **Admin panel** — product management, price editing, Shopify sync

## Shopify Integration

- Products synced from Shopify (canonical source of truth)
- Legacy web UI checkout creates a Shopify Draft Order tagged `POS, in-store, tab-tracker`
- **NEW** POS Extension checkout pushes items directly into the POS cart via Cart API — no draft orders needed
- Cashier completes payment in native Shopify POS checkout

---

## Quick Start

### Backend (Docker or venv)

```bash
# Clone and branch
git clone git@github.com:imichelena/tab-tracker.git
cd tab-tracker
git checkout feat/pos-extension

# Option A: venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create database
sudo -u postgres psql -c "CREATE USER tabtracker WITH PASSWORD 'tabtracker';"
sudo -u postgres psql -c "CREATE DATABASE tabtracker OWNER tabtracker;"

# Initialize schema (includes new pos_extension migration)
python init_db.py
psql -U tabtracker -d tabtracker -f migrations/002_pos_extension.sql

# Set required env vars (see Configuration section below)
export TAB_TRACKER_API_KEY=your-pos-extension-api-key
export POS_EXTENSION_ORIGIN=http://localhost:8095

# Run
uvicorn app:app --host 0.0.0.0 --port 8095
```

### POS Extension (Shopify CLI v3)

```bash
cd extension
npm install
# Start dev server and tunnel:
npm run dev
# This launches Shopify CLI which connects to your dev store.
# The extension will be hot-reloadable on POS devices assigned to the dev store.
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for full production deployment steps.

---

## Configuration Reference

All configuration is via environment variables (see `.env.example` for defaults).

| Variable | Description | Required | Default | Example |
|----------|-------------|----------|---------|---------|
| `TAB_TRACKER_DB` | Async PostgreSQL connection string | Optional | `postgresql+asyncpg://tabtracker:tabtracker@127.0.0.1:5432/tabtracker` | `postgresql+asyncpg://user:pass@dbhost:5432/tabtracker` |
| `TAB_TRACKER_SYNC_DB` | Sync PostgreSQL connection string (for scripts) | Optional | `postgresql+psycopg2://tabtracker:tabtracker@127.0.0.1:5432/tabtracker` | `postgresql+psycopg2://user:pass@dbhost:5432/tabtracker` |
| `SECRET_KEY` | Session signing key | Optional | `tab-tracker-poc-secret-change-me` | `your-random-64-char-secret` |
| `TAB_TRACKER_PORT` | Backend HTTP listen port | Optional | `8095` | `8095` |
| `SHOPIFY_MOCK` | Run in mock mode (no real Shopify calls) | Optional | `true` | `true` / `false` |
| `SHOPIFY_STORE_DOMAIN` | Shopify store domain | Optional (required in prod) | `""` | `amsterdam-baking-company.myshopify.com` |
| `SHOPIFY_ADMIN_TOKEN` | Shopify Admin API token | Optional (required in prod) | `""` | `shpat_your_admin_api_token_here` |
| `SHOPIFY_LOCATION_ID` | Shopify location ID for the store | Optional | `""` | `123456` |
| `TAB_TRACKER_API_KEY` | Shared API key for POS Extension auth | **Required** | `pos-extension-pilot-key-2026` | `your-generated-api-key` |
| `POS_EXTENSION_ORIGIN` | CORS allowed origin for extension requests | Optional | `*` | `https://amsterdam-baking-company.myshopify.com` |
| `CHECKOUT_METHOD` | Checkout mode: `pos_extension` or `draft_order` (legacy) | Optional | `pos_extension` | `pos_extension` |
| `SHOPIFY_SESSION_SECRET` | Shopify session secret for JWT token verification | Optional (pilot) | `""` | `your-shopify-session-secret` |

**Source:** [`config.py`](config.py), [`.env.example`](.env.example)

> ⚠️ **Security note:** The defaults in `.env.example` include placeholder database credentials and a known API key fallback. **Replace all defaults before production deployment.** See [docs/SECURITY_REPORT.md](docs/SECURITY_REPORT.md) for full audit findings.

---

## Development Workflow

```bash
# 1. Clone and branch
git clone git@github.com:imichelena/tab-tracker.git
cd tab-tracker
git checkout feat/pos-extension

# 2. Backend (terminal 1)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Set env vars (at minimum TAB_TRACKER_API_KEY)
export TAB_TRACKER_API_KEY=test-key
uvicorn app:app --reload --host 0.0.0.0 --port 8095

# 3. Extension (terminal 2)
cd extension
npm install
npm run dev
# Opens Shopify CLI tunnel; install extension on dev store POS

# 4. Static analysis
# Backend:
python3 -m py_compile app.py
# Extension:
cd extension && npx tsc --noEmit && npm run build
```

---

## Known Issues / Follow-Up

The following items are documented in full in the [Security Audit Report](docs/SECURITY_REPORT.md) and [QA Report](docs/QA_REPORT.md):

| ID | Severity | Issue | Status |
|----|----------|-------|--------|
| **SEC-003** | 🔴 High | **Shopify JWT session verification not implemented.** The `verify_api_key` dependency checks only the shared `X-API-Key` header. SPEC §7.2 mandates a dual auth chain (API key + Shopify session JWT). The pilot operates on API-key-only auth. | Pending — requires `pyjwt` dependency and `verify_shopify_token()` Depends |
| **SEC-007** | 🟡 Medium | **No rate limiting** on any API endpoint. Write endpoints (POST/PATCH/DELETE) and auth endpoints can be flooded. | Pending — `slowapi` or `starlette-limiter` integration |
| **SEC-010** | 🟢 Low | **Default DB credentials** in `.env.example` (`tabtracker:tabtracker`). Must override via env vars in production. | Documented — replace before prod |
| **T-16** | 📋 Follow-up | **Testing documentation** to be added per PM_REPORT breakdown. | Pending |

For full evidence and remediation guidance, see:
- [docs/SECURITY_REPORT.md](docs/SECURITY_REPORT.md) — 17 findings including SEC-001 (Critical, now fixed), SEC-003, SEC-007, SEC-008 (now fixed), SEC-010
- [docs/QA_REPORT.md](docs/QA_REPORT.md) — Test case matrix, pass/fail breakdown, acceptance criteria
- [docs/STATUS.md](docs/STATUS.md) — Current build state, verified/not-verified tables, gate verdicts, production-readiness checklist
- [docs/TESTING.md](docs/TESTING.md) — Live test plan: backend smoke tests, integration tests, end-to-end POS flow, rollback steps
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — Operational gotchas: port conflicts, CORS, Cart API quirks, migration details

---

## API Documentation

Full API reference is at **[docs/API.md](docs/API.md)** — covers all 12 `/api/v1/*` endpoints with request/response schemas, authentication details, and the Cart API contract.

---

## Deployment Guide

Step-by-step deployment instructions are at **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** — backend VPS setup, DB migration, extension deployment via Shopify CLI, rollback procedure, and smoke tests.

---

## License

Private — Amsterdam Baking Company
