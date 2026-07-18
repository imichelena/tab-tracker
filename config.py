"""
Configuration for Tab Tracker.
Environment variables override defaults.
"""
import os

DATABASE_URL = os.environ.get(
    "TAB_TRACKER_DB",
    "postgresql+asyncpg://tabtracker:tabtracker@127.0.0.1:5432/tabtracker"
)

SYNC_DB_URL = os.environ.get(
    "TAB_TRACKER_SYNC_DB",
    "postgresql+psycopg2://tabtracker:tabtracker@127.0.0.1:5432/tabtracker"
)

SECRET_KEY = os.environ.get("SECRET_KEY", "tab-tracker-poc-secret-change-me")
SESSION_COOKIE_NAME = "tabtracker_session"

# Shopify config (mock for POC, real values set later)
SHOPIFY_STORE_DOMAIN = os.environ.get("SHOPIFY_STORE_DOMAIN", "")
SHOPIFY_ADMIN_TOKEN = os.environ.get("SHOPIFY_ADMIN_TOKEN", "")
SHOPIFY_LOCATION_ID = os.environ.get("SHOPIFY_LOCATION_ID", "")
SHOPIFY_MOCK = os.environ.get("SHOPIFY_MOCK", "true").lower() == "true"

APP_PORT = int(os.environ.get("TAB_TRACKER_PORT", "8095"))
