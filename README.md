# Tab Tracker

Tablet-optimized restaurant table tab tracking system for Amsterdam Baking Company.

Tracks open tabs, facilitates fast product selection, and hands off the bill to Shopify as a draft order (tagged as POS/in-store sale) for checkout.

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
- Checkout creates a Shopify Draft Order tagged `POS, in-store, tab-tracker`
- Cashier completes payment in Shopify POS

## License

Private — Amsterdam Baking Company
