-- Tab Tracker POS Extension — DB migration 002
-- Adds pos_sessions table, new columns on tabs and transactions.
-- Apply: psql -U tabtracker -d tabtracker -f migrations/002_pos_extension.sql
-- Rollback instructions at end of file.

BEGIN;

-- 1. New table: pos_sessions
-- Tracks which POS terminal opened which tab, for audit and multi-terminal support.
CREATE TABLE IF NOT EXISTS tab_tracker.pos_sessions (
    id SERIAL PRIMARY KEY,
    shop_id INTEGER REFERENCES tab_tracker.shops(id),
    pos_terminal_id VARCHAR(100),        -- Shopify device ID
    staff_id VARCHAR(100),               -- Shopify staff ID
    opened_tab_ids INTEGER[],            -- Array of currently open tab IDs
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- 2. New columns on tabs table
ALTER TABLE tab_tracker.tabs
  ADD COLUMN IF NOT EXISTS pos_cart_sent_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS pos_terminal_id VARCHAR(100);

-- 3. New columns on transactions table
ALTER TABLE tab_tracker.transactions
  ADD COLUMN IF NOT EXISTS pos_order_id VARCHAR(100),
  ADD COLUMN IF NOT EXISTS pos_terminal_id VARCHAR(100),
  ADD COLUMN IF NOT EXISTS checkout_method VARCHAR(20) DEFAULT 'pos_extension';

COMMIT;

-- ──────────────────────────────────────────────────
-- Rollback (if needed):
--   ALTER TABLE tab_tracker.transactions DROP COLUMN IF EXISTS checkout_method;
--   ALTER TABLE tab_tracker.transactions DROP COLUMN IF EXISTS pos_terminal_id;
--   ALTER TABLE tab_tracker.transactions DROP COLUMN IF EXISTS pos_order_id;
--   ALTER TABLE tab_tracker.tabs DROP COLUMN IF EXISTS pos_terminal_id;
--   ALTER TABLE tab_tracker.tabs DROP COLUMN IF EXISTS pos_cart_sent_at;
--   DROP TABLE IF EXISTS tab_tracker.pos_sessions;
-- ──────────────────────────────────────────────────
