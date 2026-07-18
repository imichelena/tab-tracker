"""SQLAlchemy models — all under tab_tracker schema."""
from sqlalchemy import (
    Column, Integer, String, Boolean, Text, DECIMAL, ForeignKey, DateTime, UniqueConstraint, JSON
)
from sqlalchemy.sql import func
from database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "tab_tracker"}

    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(200), nullable=False)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Shop(Base):
    __tablename__ = "shops"
    __table_args__ = {"schema": "tab_tracker"}

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    has_tables = Column(Boolean, default=False)
    shopify_location_id = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Table(Base):
    __tablename__ = "tables"
    __table_args__ = (
        UniqueConstraint("shop_id", "name"),
        {"schema": "tab_tracker"},
    )

    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("tab_tracker.shops.id"), nullable=False)
    name = Column(String(50), nullable=False)
    seats = Column(Integer, default=4)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = {"schema": "tab_tracker"}

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    icon = Column(String(10), default="🍽️")
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = {"schema": "tab_tracker"}

    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("tab_tracker.categories.id"))
    name = Column(String(200), nullable=False)
    slug = Column(String(200))
    price = Column(DECIMAL(10, 2), nullable=False)
    currency = Column(String(3), default="EUR")
    image_path = Column(String(500))
    shopify_variant_id = Column(String(50))
    shopify_product_id = Column(String(50))
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Tab(Base):
    __tablename__ = "tabs"
    __table_args__ = {"schema": "tab_tracker"}

    id = Column(Integer, primary_key=True)
    table_id = Column(Integer, ForeignKey("tab_tracker.tables.id"), nullable=False)
    shop_id = Column(Integer, ForeignKey("tab_tracker.shops.id"), nullable=False)
    status = Column(String(20), default="open")  # open, sent, closed
    guests = Column(Integer, default=1)
    opened_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_at = Column(DateTime(timezone=True))
    opened_by = Column(Integer, ForeignKey("tab_tracker.users.id"))
    shopify_draft_order_id = Column(String(50))
    sent_at = Column(DateTime(timezone=True))
    notes = Column(Text)


class TabItem(Base):
    __tablename__ = "tab_items"
    __table_args__ = {"schema": "tab_tracker"}

    id = Column(Integer, primary_key=True)
    tab_id = Column(Integer, ForeignKey("tab_tracker.tabs.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("tab_tracker.products.id"))
    product_name = Column(String(200), nullable=False)
    unit_price = Column(DECIMAL(10, 2), nullable=False)
    quantity = Column(Integer, default=1)
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    added_by = Column(Integer, ForeignKey("tab_tracker.users.id"))


class SyncLog(Base):
    __tablename__ = "sync_log"
    __table_args__ = {"schema": "tab_tracker"}

    id = Column(Integer, primary_key=True)
    synced_at = Column(DateTime(timezone=True), server_default=func.now())
    synced_by = Column(Integer, ForeignKey("tab_tracker.users.id"))
    products_added = Column(Integer, default=0)
    products_updated = Column(Integer, default=0)
    products_unchanged = Column(Integer, default=0)
    status = Column(String(20), default="success")
    message = Column(Text)


class PriceOverride(Base):
    """Translation/override rules for POS pricing.
    Maps a display product to a different price and checkout variant."""
    __tablename__ = "price_overrides"
    __table_args__ = {"schema": "tab_tracker"}

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("tab_tracker.products.id"), nullable=False)
    override_price = Column(DECIMAL(10, 2), nullable=False)
    checkout_variant_id = Column(String(50))  # Shopify variant to use for cart permalink
    checkout_product_name = Column(String(200))  # Name shown on Shopify checkout
    rule_name = Column(String(200))  # Human-readable rule description
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Transaction(Base):
    """Permanent record of a completed/sent tab — the business transaction.
    Created when a tab is sent to Shopify. Survives tab deletion."""
    __tablename__ = "transactions"
    __table_args__ = {"schema": "tab_tracker"}

    id = Column(Integer, primary_key=True)
    tab_id = Column(Integer, ForeignKey("tab_tracker.tabs.id", ondelete="SET NULL"))
    table_id = Column(Integer, ForeignKey("tab_tracker.tables.id"))
    table_name = Column(String(50))  # snapshot — table name at time of transaction
    shop_id = Column(Integer, ForeignKey("tab_tracker.shops.id"))
    shop_name = Column(String(200))  # snapshot
    cashier_id = Column(Integer, ForeignKey("tab_tracker.users.id"))
    cashier_name = Column(String(200))  # snapshot
    guest_count = Column(Integer, default=1)

    # Financial
    total_amount = Column(DECIMAL(10, 2), nullable=False)
    currency = Column(String(3), default="EUR")
    item_count = Column(Integer, default=0)

    # Shopify link
    shopify_draft_order_id = Column(String(100))
    shopify_status = Column(String(20), default="sent")  # sent, completed, voided

    # Timing
    opened_at = Column(DateTime(timezone=True))  # when tab was opened
    sent_at = Column(DateTime(timezone=True), server_default=func.now())  # when sent to Shopify
    completed_at = Column(DateTime(timezone=True))  # when Shopify order was paid

    # Notes
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TransactionItem(Base):
    """Line items for a transaction — permanent snapshot of what was ordered."""
    __tablename__ = "transaction_items"
    __table_args__ = {"schema": "tab_tracker"}

    id = Column(Integer, primary_key=True)
    transaction_id = Column(Integer, ForeignKey("tab_tracker.transactions.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer)  # snapshot, no FK (product may be deleted)
    product_name = Column(String(200), nullable=False)  # original display name
    checkout_name = Column(String(200))  # name sent to Shopify (e.g. "1 x Empanada")
    unit_price = Column(DECIMAL(10, 2), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    line_total = Column(DECIMAL(10, 2), nullable=False)
    flavor = Column(String(200))  # flavor note for override products (e.g. "Caprese empanadas")
    shopify_variant_id = Column(String(50))  # variant used for this line
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
