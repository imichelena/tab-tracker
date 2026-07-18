# Tab Tracker POS Extension — Deployment Guide

**Branch:** `feat/pos-extension`
**Repo:** `git@github.com:imichelena/tab-tracker.git`
**Backend target VPS:** `178.104.146.136` (Tailscale `100.122.187.17`)
**Shopify store:** `amsterdam-baking-company.myshopify.com`

---

## Table of Contents

1. [Backend Deployment](#1-backend-deployment)
2. [Extension Deployment](#2-extension-deployment)
3. [Database Migration](#3-database-migration)
4. [Smoke Tests](#4-smoke-tests)
5. [Rollback Procedure](#5-rollback-procedure)

---

## 1. Backend Deployment

### 1.1 Prerequisites

- Python 3.11+
- PostgreSQL 14+ with `tabtracker` database and `tab_tracker` schema
- `venv` (Python virtual environment)
- nginx (reverse proxy, currently serving on `:8090`)
- gunicorn (WSGI server, currently serving on `:8095`)
- systemd service for `tab-tracker`

### 1.2 Pull the Branch

```bash
ssh deploy@178.104.146.136  # or via Tailscale: ssh deploy@100.122.187.17
cd /opt/tab-tracker
git fetch origin
git checkout feat/pos-extension
git pull origin feat/pos-extension
```

### 1.3 Set Environment Variables

Edit the application env file (e.g. `/opt/tab-tracker/.env` or `/etc/systemd/system/tab-tracker.service`):

```bash
# Required for POS Extension
TAB_TRACKER_API_KEY=<your-generated-api-key>

# CORS origin — must match the Shopify store domain in production
POS_EXTENSION_ORIGIN=https://amsterdam-baking-company.myshopify.com

# Checkout method (pos_extension is the default)
CHECKOUT_METHOD=pos_extension

# Shopify session secret (optional for pilot, required when JWT verification is implemented)
SHOPIFY_SESSION_SECRET=<your-shopify-session-secret>

# Existing vars — keep current production values
TAB_TRACKER_DB=postgresql+asyncpg://tabtracker:<password>@127.0.0.1:5432/tabtracker
TAB_TRACKER_SYNC_DB=postgresql+psycopg2://tabtracker:<password>@127.0.0.1:5432/tabtracker
SECRET_KEY=<your-session-secret>
SHOPIFY_STORE_DOMAIN=amsterdam-baking-company.myshopify.com
SHOPIFY_ADMIN_TOKEN=shpat_<your-admin-token>
SHOPIFY_LOCATION_ID=<your-location-id>
```

> **Source:** [`.env.example`](../.env.example), [`config.py`](../config.py)

### 1.4 Apply Database Migration

```bash
cd /opt/tab-tracker
psql -U tabtracker -d tabtracker -f migrations/002_pos_extension.sql
```

**Expected output:**
```
BEGIN
CREATE TABLE
ALTER TABLE
ALTER TABLE
ALTER TABLE
COMMIT
```

### 1.5 Verify Migration

```bash
# Check new table exists
psql -U tabtracker -d tabtracker -c "\dt tab_tracker.pos_sessions"

# Expected:
#           List of relations
#  Schema  |    Name      | Type  |  Owner
# ---------+--------------+-------+---------
#  tab_tracker | pos_sessions | table | tabtracker

# Check new columns on tabs
psql -U tabtracker -d tabtracker -c "\d tab_tracker.tabs"
# Expect: pos_cart_sent_at (timestamptz), pos_terminal_id (varchar)

# Check new columns on transactions
psql -U tabtracker -d tabtracker -c "\d tab_tracker.transactions"
# Expect: pos_order_id (varchar), pos_terminal_id (varchar), checkout_method (varchar, default 'pos_extension')
```

See [`migrations/002_pos_extension.sql`](../migrations/002_pos_extension.sql) for the full migration source.

### 1.6 Install Python Dependencies

```bash
cd /opt/tab-tracker
source .venv/bin/activate
pip install -r requirements.txt
```

### 1.7 Restart the Service

```bash
sudo systemctl restart tab-tracker
sudo systemctl status tab-tracker
# Confirm: "active (running)"
```

If gunicorn is configured directly (no systemd wrapper):

```bash
# Kill existing gunicorn and restart
pkill -f "gunicorn.*app:app"
cd /opt/tab-tracker
source .venv/bin/activate
gunicorn app:app --bind 0.0.0.0:8095 --workers 4 --timeout 120 \
  --access-logfile /var/log/tab-tracker/access.log \
  --error-logfile /var/log/tab-tracker/error.log \
  --daemon
```

---

## 2. Extension Deployment

### 2.1 Prerequisites

- [Shopify Partners](https://partners.shopify.com) account
- [Shopify CLI](https://shopify.dev/docs/api/shopify-cli) v3 installed (`npm install -g @shopify/cli`)
- Development store created in Partners dashboard (e.g., `amsterdam-baking-company.myshopify.com`)
- Custom app created in Partners dashboard (type: **POS-only custom app**, no webhooks or OAuth redirects)

### 2.2 Install the Extension on the Dev Store

```bash
cd /opt/tab-tracker/extension
npm install

# Start the Shopify CLI development tunnel
npm run dev
```

The Shopify CLI will:
1. Prompt you to log in to your Partners account
2. Select the `amsterdam-baking-company` development store
3. Deploy the extension to a temporary URL
4. Provide instructions for installing the extension on a POS device

### 2.3 Configure Extension Settings

The extension reads three settings from `shopify.extension.toml` (defined in the `[[extensions.settings]]` block). **These MUST be set before production deployment** — without them the extension throws an error at startup:

| Setting Key | Description | Example Value |
|-------------|-------------|---------------|
| `backend_url` | Tab Tracker backend API URL | `https://api.example.com` (or `http://178.104.146.136:8095` internally) |
| `api_key` | Backend API key matching `TAB_TRACKER_API_KEY` env var | `your-generated-api-key` |
| `default_terminal_id` | Default POS terminal identifier for tab operations | `pos-terminal-01` |

Settings are configured in the Shopify Partners dashboard under the custom app's **Extensions** tab, or via the `shopify app config push` command.

**Source:** [`extension/shopify.extension.toml`](../extension/shopify.extension.toml)

### 2.4 Install on POS Device

1. On the Shopify POS device, open **Settings → Extensions**
2. Find the **Tab Tracker** extension
3. Tap **Install**
4. The Tab Tracker tile appears on the POS home screen
5. Tap the tile to open the full tab-management modal

### 2.5 Test on Dev Store POS

1. Open the Tab Tracker modal on the POS device
2. Verify the product catalog loads (GET /api/v1/products)
3. Select a table → open a tab → add items
4. Tap **Send to POS Cart** — items should appear in the native POS cart
5. Complete checkout — verify a `pos_extension` transaction record is created

### 2.6 Production Deploy

```bash
cd /opt/tab-tracker/extension
npm install

# Build production bundle
npm run build

# Deploy via Shopify CLI
shopify app deploy
```

The `shopify app deploy` command uploads the extension to the Shopify Partners platform and makes it available to all POS devices assigned to the production store.

---

## 3. Database Migration

Migration `002_pos_extension.sql` adds three changes:

### 3.1 New Table: `tab_tracker.pos_sessions`

Tracks which POS terminal and staff member opened which tabs.

```
Column           | Type           | Description
-----------------|----------------|------------------------
id               | SERIAL PK      | Primary key
shop_id          | INTEGER (FK)   | References tab_tracker.shops
pos_terminal_id  | VARCHAR(100)   | Shopify POS device ID
staff_id         | VARCHAR(100)   | Shopify staff ID
opened_tab_ids   | INTEGER[]      | Array of opened tab IDs
created_at       | TIMESTAMPTZ    | Row creation timestamp
updated_at       | TIMESTAMPTZ    | Last update timestamp
```

### 3.2 New Columns on `tab_tracker.tabs`

- `pos_cart_sent_at TIMESTAMPTZ` — when the tab was sent to the POS cart
- `pos_terminal_id VARCHAR(100)` — which terminal sent it

### 3.3 New Columns on `tab_tracker.transactions`

- `pos_order_id VARCHAR(100)` — Shopify POS order ID (set after checkout completes)
- `pos_terminal_id VARCHAR(100)` — originating POS terminal
- `checkout_method VARCHAR(20) DEFAULT 'pos_extension'` — distinguishes POS extension from legacy draft-order checkouts

### 3.4 Web UI Compatibility

The migration is **fully additive** — no columns were modified, renamed, or dropped. All existing web UI templates (`floor.html`, `admin.html`, `history.html`) and their associated HTMX endpoints continue to work unchanged.

---

## 4. Smoke Tests

After deployment, verify the backend is operational:

```bash
# Health check
curl http://localhost:8095/health
# Expected: {"status":"ok","service":"tab-tracker","shopify_mock":false}

# Products endpoint
curl -H "X-API-Key: your-generated-api-key" http://localhost:8095/api/v1/products
# Expected: JSON array of active products with id, name, price, category, override_price

# Categories endpoint
curl -H "X-API-Key: your-generated-api-key" http://localhost:8095/api/v1/categories
# Expected: JSON array of active categories with id, name, icon, sort_order

# Open tabs endpoint
curl -H "X-API-Key: your-generated-api-key" http://localhost:8095/api/v1/tabs/open
# Expected: JSON array of open tabs (may be empty — that's fine)

# 401 test (missing API key)
curl http://localhost:8095/api/v1/products
# Expected: 401 {"detail":"Invalid or missing API key"}
```

---

## 5. Rollback Procedure

Since the migration is additive (new table + new columns only), rollback is safe and non-destructive.

### 5.1 Revert Code

```bash
cd /opt/tab-tracker
git revert HEAD  # or specify the specific commit
git push origin feat/pos-extension
```

### 5.2 Restart Backend

```bash
sudo systemctl restart tab-tracker
```

### 5.3 Optionally Revert Database

**Note:** Reverting the database is optional — the new table and columns are unused by the legacy web UI and cause no harm. If you want a full revert:

```sql
ALTER TABLE tab_tracker.transactions DROP COLUMN IF EXISTS checkout_method;
ALTER TABLE tab_tracker.transactions DROP COLUMN IF EXISTS pos_terminal_id;
ALTER TABLE tab_tracker.transactions DROP COLUMN IF EXISTS pos_order_id;
ALTER TABLE tab_tracker.tabs DROP COLUMN IF EXISTS pos_terminal_id;
ALTER TABLE tab_tracker.tabs DROP COLUMN IF EXISTS pos_cart_sent_at;
DROP TABLE IF EXISTS tab_tracker.pos_sessions;
```

(See rollback comments at end of [`migrations/002_pos_extension.sql`](../migrations/002_pos_extension.sql))

### 5.4 Rollback Extension

```bash
cd /opt/tab-tracker/extension
# Deploy the previous (non-POS) version
shopify app deploy  # with the previous app version selected
# OR: Disable the extension in Shopify Partners dashboard
```

---

**API Reference:** See [`docs/API.md`](API.md) for complete endpoint documentation.
