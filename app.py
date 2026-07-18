"""
Tab Tracker — FastAPI main app.
Tablet-optimized restaurant tab tracking for Amsterdam Baking Company.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from decimal import Decimal

from fastapi import FastAPI, Request, Depends, HTTPException, Form, Query, Header
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.cors import CORSMiddleware
from sqlalchemy import select, func as sql_func, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from config import (
    SECRET_KEY, SESSION_COOKIE_NAME, SHOPIFY_MOCK,
    TAB_TRACKER_API_KEY, POS_EXTENSION_ORIGIN, CHECKOUT_METHOD, SHOPIFY_SESSION_SECRET,
)
import os as _os
TRANSACTION_API_KEY = _os.environ.get("TRANSACTION_API_KEY", "abc-bakery-analytics-2026")
from database import get_db, engine, Base
from models import User, Shop, Table, Category, Product, Tab, TabItem, SyncLog, PriceOverride, Transaction, TransactionItem, PosSession
from auth import hash_password, verify_password, get_current_user
from shopify import create_draft_order, sync_products
from jinja import _render

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
logger = logging.getLogger("tabtracker")

app = FastAPI(title="Tab Tracker")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, session_cookie=SESSION_COOKIE_NAME)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[POS_EXTENSION_ORIGIN] if POS_EXTENSION_ORIGIN != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ─── Auth dependency ───
async def require_user(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user

async def require_admin(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ─── POS Extension API Auth ───

async def verify_api_key(
    request: Request,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    x_shop_location: str | None = Header(None, alias="X-Shop-Location"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Require X-API-Key header on all /api/v1/* endpoints.
    Returns auth context dict with shop_id resolved from X-Shop-Location."""
    if not x_api_key or x_api_key != TAB_TRACKER_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    # Resolve shop_id from X-Shop-Location header
    shop_id = None
    if x_shop_location:
        result = await db.execute(
            select(Shop).where(Shop.shopify_location_id == x_shop_location)
        )
        shop = result.scalar_one_or_none()
        if shop:
            shop_id = shop.id
        else:
            # Fallback: try matching by name or just use the first active shop
            result = await db.execute(select(Shop).where(Shop.has_tables == True))
            first_shop = result.scalars().first()
            if first_shop:
                shop_id = first_shop.id
    else:
        # No location header — use default shop (single shop pilot)
        result = await db.execute(select(Shop).where(Shop.has_tables == True))
        first_shop = result.scalars().first()
        if first_shop:
            shop_id = first_shop.id

    return {"shop_id": shop_id, "location_id": x_shop_location}


# ─── Routes ───

@app.get("/health")
async def health():
    return {"status": "ok", "service": "tab-tracker", "shopify_mock": SHOPIFY_MOCK}


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/", status_code=303)
    return HTMLResponse(_render("login.html", request=request, error=None))


@app.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        return HTMLResponse(_render("login.html", request=request, error="Invalid credentials"))
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["display_name"] = user.display_name
    request.session["is_admin"] = user.is_admin
    return RedirectResponse(url="/", status_code=303)


@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


# ─── Main floor view ───

@app.get("/", response_class=HTMLResponse)
async def floor(
    request: Request,
    active_table_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    # Get the table shop
    result = await db.execute(select(Shop).where(Shop.has_tables == True))
    shops = result.scalars().all()
    if not shops:
        return HTMLResponse("<h1>No shop with tables configured.</h1>")

    shop = shops[0]  # POC: single shop with tables

    # Get all tables for this shop
    result = await db.execute(
        select(Table).where(Table.shop_id == shop.id, Table.is_active == True)
        .order_by(Table.sort_order, Table.name)
    )
    tables = result.scalars().all()

    # Get open tabs for all tables (to show status)
    result = await db.execute(
        select(Tab).where(Tab.shop_id == shop.id, Tab.status == "open")
    )
    open_tabs = {t.table_id: t for t in result.scalars().all()}

    # Get tab totals for open tabs
    tab_totals = {}
    if open_tabs:
        for tab in open_tabs.values():
            result = await db.execute(
                select(sql_func.coalesce(sql_func.sum(TabItem.unit_price * TabItem.quantity), 0))
                .where(TabItem.tab_id == tab.id)
            )
            tab_totals[tab.table_id] = float(result.scalar())

    # Get categories with products
    result = await db.execute(
        select(Category).where(Category.is_active == True).order_by(Category.sort_order, Category.name)
    )
    categories = result.scalars().all()

    # Get all active products grouped by category
    # Also load active price overrides
    result = await db.execute(
        select(PriceOverride).where(PriceOverride.is_active == True)
    )
    overrides = {o.product_id: o for o in result.scalars().all()}

    products_by_cat = {}
    for cat in categories:
        result = await db.execute(
            select(Product).where(Product.category_id == cat.id, Product.is_active == True)
            .order_by(Product.sort_order, Product.name)
        )
        products_by_cat[cat.id] = result.scalars().all()

    # Get active tab + items if a table is selected
    active_tab = None
    active_tab_items = []
    active_tab_total = 0.0

    if active_table_id:
        # Find or create open tab for this table
        if active_table_id in open_tabs:
            active_tab = open_tabs[active_table_id]
        else:
            # Check table exists
            result = await db.execute(select(Table).where(Table.id == active_table_id))
            if result.scalar_one_or_none():
                active_tab = Tab(
                    table_id=active_table_id,
                    shop_id=shop.id,
                    status="open",
                    opened_by=user["id"],
                )
                db.add(active_tab)
                await db.commit()
                await db.refresh(active_tab)
                open_tabs[active_table_id] = active_tab
                tab_totals[active_table_id] = 0.0

        if active_tab:
            result = await db.execute(
                select(TabItem).where(TabItem.tab_id == active_tab.id).order_by(TabItem.added_at)
            )
            active_tab_items = result.scalars().all()
            active_tab_total = sum(float(item.unit_price) * item.quantity for item in active_tab_items)

    return HTMLResponse(_render("floor.html",
        request=request,
        user=user,
        shop=shop,
        tables=tables,
        open_tabs=open_tabs,
        tab_totals=tab_totals,
        categories=categories,
        products_by_cat=products_by_cat,
        active_table_id=active_table_id,
        active_tab=active_tab,
        active_tab_items=active_tab_items,
        active_tab_total=active_tab_total,
        overrides=overrides,
        shopify_mock=SHOPIFY_MOCK,
    ))


# ─── HTMX endpoints (no full page reload) ───

@app.post("/api/tabs/{tab_id}/items", response_class=HTMLResponse)
async def add_item(
    tab_id: int,
    product_id: int = Form(...),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    # Get product
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        return HTMLResponse("Product not found", status_code=404)

    # Check for price override
    override_result = await db.execute(
        select(PriceOverride).where(
            PriceOverride.product_id == product_id,
            PriceOverride.is_active == True
        )
    )
    override = override_result.scalar_one_or_none()
    unit_price = override.override_price if override else product.price

    # Check for existing line item with same product AND same price
    result = await db.execute(
        select(TabItem).where(
            TabItem.tab_id == tab_id,
            TabItem.product_id == product_id,
            TabItem.unit_price == unit_price
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.quantity += 1
    else:
        item = TabItem(
            tab_id=tab_id,
            product_id=product_id,
            product_name=product.name,
            unit_price=unit_price,
            quantity=1,
            added_by=user["id"],
        )
        db.add(item)

    await db.commit()

    # Return updated bill
    return await _render_bill(tab_id, db)


@app.put("/api/tabs/{tab_id}/items/{item_id}", response_class=HTMLResponse)
async def update_item_qty(
    tab_id: int,
    item_id: int,
    action: str = Form(...),  # "inc" or "dec"
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    result = await db.execute(select(TabItem).where(TabItem.id == item_id, TabItem.tab_id == tab_id))
    item = result.scalar_one_or_none()
    if not item:
        return HTMLResponse("Item not found", status_code=404)

    if action == "inc":
        item.quantity += 1
    elif action == "dec":
        item.quantity -= 1
        if item.quantity <= 0:
            await db.delete(item)

    await db.commit()
    return await _render_bill(tab_id, db)


@app.delete("/api/tabs/{tab_id}/items/{item_id}", response_class=HTMLResponse)
async def delete_item(
    tab_id: int,
    item_id: int,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    result = await db.execute(select(TabItem).where(TabItem.id == item_id, TabItem.tab_id == tab_id))
    item = result.scalar_one_or_none()
    if item:
        await db.delete(item)
        await db.commit()

    return await _render_bill(tab_id, db)


@app.post("/api/tabs/{tab_id}/send-to-shopify", response_class=HTMLResponse)
async def send_to_shopify(
    tab_id: int,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    # Get tab + items
    result = await db.execute(select(Tab).where(Tab.id == tab_id))
    tab = result.scalar_one_or_none()
    if not tab:
        return HTMLResponse("Tab not found", status_code=404)

    result = await db.execute(select(TabItem).where(TabItem.tab_id == tab_id).order_by(TabItem.added_at))
    items = result.scalars().all()

    if not items:
        return HTMLResponse("Cannot send empty tab", status_code=400)

    # Build payload
    shopify_items = []
    total = 0.0
    for item in items:
        # Get product for variant ID
        product = None
        if item.product_id:
            res = await db.execute(select(Product).where(Product.id == item.product_id))
            product = res.scalar_one_or_none()

        # Check for override checkout variant
        checkout_variant = product.shopify_variant_id if product else None
        checkout_name = item.product_name
        if product:
            ov_result = await db.execute(
                select(PriceOverride).where(
                    PriceOverride.product_id == product.id,
                    PriceOverride.is_active == True
                )
            )
            ov = ov_result.scalar_one_or_none()
            if ov:
                if ov.checkout_variant_id:
                    checkout_variant = ov.checkout_variant_id
                if ov.checkout_product_name:
                    checkout_name = ov.checkout_product_name

        # Track flavor info: if override changes the name, preserve original as flavor
        original_name = item.product_name
        flavor_note = None
        if checkout_name != original_name:
            flavor_note = original_name

        shopify_items.append({
            "product_name": checkout_name,
            "quantity": item.quantity,
            "unit_price": float(item.unit_price),
            "shopify_variant_id": checkout_variant,
            "properties": [{"name": "Flavor", "value": flavor_note}] if flavor_note else [],
        })
        total += float(item.unit_price) * item.quantity

    # Call Shopify - create draft order with write_draft_orders scope
    result = await create_draft_order(tab_id, shopify_items, total)

    if result["success"]:
        tab.status = "sent"
        tab.shopify_draft_order_id = str(result["draft_order_id"])
        tab.sent_at = datetime.now(timezone.utc)

        # ─── Snapshot into permanent transaction record ───
        # Get table name
        table_name = None
        table_id = None
        if tab.table_id:
            tbl_res = await db.execute(select(Table).where(Table.id == tab.table_id))
            tbl = tbl_res.scalar_one_or_none()
            if tbl:
                table_name = tbl.name
                table_id = tbl.id

        # Get shop name
        shop_name = None
        shop_res = await db.execute(select(Shop).where(Shop.id == tab.shop_id))
        shop_obj = shop_res.scalar_one_or_none()
        if shop_obj:
            shop_name = shop_obj.name

        # Get cashier name
        cashier_name = None
        if user and user.get("id"):
            usr_res = await db.execute(select(User).where(User.id == user["id"]))
            usr_obj = usr_res.scalar_one_or_none()
            if usr_obj:
                cashier_name = usr_obj.display_name

        item_count = sum(item.quantity for item in items)
        tx = Transaction(
            tab_id=tab.id,
            table_id=table_id,
            table_name=table_name,
            shop_id=tab.shop_id,
            shop_name=shop_name,
            cashier_id=user.get("id") if user else None,
            cashier_name=cashier_name,
            guest_count=tab.guests,
            total_amount=Decimal(str(f"{total:.2f}")),
            currency="EUR",
            item_count=item_count,
            shopify_draft_order_id=str(result["draft_order_id"]),
            shopify_status="sent",
            opened_at=tab.opened_at,
            sent_at=datetime.now(timezone.utc),
            notes=tab.notes,
        )
        db.add(tx)
        await db.flush()  # get tx.id

        # Snapshot line items
        for idx, item in enumerate(items):
            product = None
            if item.product_id:
                pres = await db.execute(select(Product).where(Product.id == item.product_id))
                product = pres.scalar_one_or_none()

            checkout_variant = product.shopify_variant_id if product else None
            checkout_name = item.product_name
            flavor_note = None
            if product:
                ov_res = await db.execute(
                    select(PriceOverride).where(
                        PriceOverride.product_id == product.id,
                        PriceOverride.is_active == True
                    )
                )
                ov = ov_res.scalar_one_or_none()
                if ov:
                    if ov.checkout_variant_id:
                        checkout_variant = ov.checkout_variant_id
                    if ov.checkout_product_name:
                        checkout_name = ov.checkout_product_name
                    if checkout_name != item.product_name:
                        flavor_note = item.product_name

            line_total = Decimal(str(item.unit_price)) * item.quantity
            tx_item = TransactionItem(
                transaction_id=tx.id,
                product_id=item.product_id,
                product_name=item.product_name,
                checkout_name=checkout_name,
                unit_price=Decimal(str(item.unit_price)),
                quantity=item.quantity,
                line_total=line_total,
                flavor=flavor_note,
                shopify_variant_id=checkout_variant,
                sort_order=idx,
            )
            db.add(tx_item)

        await db.commit()

        mock_badge = '<p class="mock-badge">MOCK MODE</p>' if result.get("mock") else ""
        return HTMLResponse(
            f'<div class="shopify-success" id="bill-content">'
            f'<div class="shopify-success-banner">'
            f'<div class="success-check">&#x2705;</div>'
            f'<h2>Sent to Shopify</h2>'
            f'<p class="success-detail">Draft Order: {result["draft_order_id"]}</p>'
            f'{mock_badge}'
            f'<p class="success-total">Total: &euro;{total:.2f}</p>'
            f'<p class="success-instruction">Draft order created in Shopify. Complete checkout in Shopify admin/POS.</p>'
            f'<button class="btn-back-floor" onclick="location.href=\'/\'">&#x1F3E0; Back to Floor</button>'
            f'</div></div>'
        )
    else:
        err_msg = result.get("error", "Unknown error")
        return HTMLResponse(
            f'<div class="shopify-error-banner">'
            f'<div style="font-size:48px;margin-bottom:8px">&#x274C;</div>'
            f'<h2>Shopify Error</h2>'
            f'<p style="color:#c62828;margin:8px 0">{err_msg}</p>'
            f'<p style="font-size:13px;color:#999;margin:8px 0 16px">Check Shopify API credentials in admin</p>'
            f'<button class="btn-back-floor" style="background:linear-gradient(135deg,#c62828,#b71c1c)" onclick="location.reload()">Try Again</button>'
            f'</div>'
        )


# ─── Admin panel ───

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if not user.get("is_admin"):
        return HTMLResponse("Forbidden", status_code=403)

    # Get stats
    result = await db.execute(select(sql_func.count()).select_from(Product))
    product_count = result.scalar()

    result = await db.execute(select(sql_func.count()).select_from(Category))
    category_count = result.scalar()

    result = await db.execute(select(sql_func.count()).where(Product.is_active == True))
    active_count = result.scalar()

    result = await db.execute(select(sql_func.count()).where(Product.is_active == False))
    inactive_count = result.scalar()

    result = await db.execute(select(sql_func.count()).select_from(Tab).where(Tab.status == "open"))
    open_tabs_count = result.scalar()

    result = await db.execute(select(sql_func.count()).select_from(Tab).where(Tab.status == "sent"))
    sent_tabs_count = result.scalar()

    # Get products with categories
    result = await db.execute(
        select(Product, Category).outerjoin(Category, Product.category_id == Category.id)
        .order_by(Category.sort_order, Product.name)
    )
    products_with_cats = result.all()

    result = await db.execute(select(Category).order_by(Category.sort_order))
    categories = result.scalars().all()

    category_names = [c.name for c in categories if c.name]
    category_counts = []
    for cat in categories:
        res = await db.execute(select(sql_func.count()).where(Product.category_id == cat.id))
        category_counts.append((cat.name, res.scalar()))

    # Get tables
    result = await db.execute(select(Shop).where(Shop.has_tables == True))
    shops = result.scalars().all()
    tables = []
    if shops:
        result = await db.execute(
            select(Table).where(Table.shop_id == shops[0].id).order_by(Table.sort_order)
        )
        tables = result.scalars().all()

    # Get sync logs
    result = await db.execute(select(SyncLog).order_by(SyncLog.synced_at.desc()).limit(10))
    sync_logs = result.scalars().all()

    # Get price overrides with product info
    result = await db.execute(
        select(PriceOverride, Product).outerjoin(Product, PriceOverride.product_id == Product.id)
        .order_by(PriceOverride.created_at.desc())
    )
    price_overrides = result.all()

    # Build override lookup dicts for product rows
    override_product_ids = set()
    override_prices = {}
    for ov, prod in price_overrides:
        if ov.is_active and prod:
            override_product_ids.add(prod.id)
            override_prices[prod.id] = ov.override_price

    # Build category product counts
    category_product_counts = {}
    for cat in categories:
        res = await db.execute(select(sql_func.count()).where(Product.category_id == cat.id))
        category_product_counts[cat.id] = res.scalar()

    # Categories that have products (can't delete if they do)
    categories_with_products = set()
    for cat in categories:
        if category_product_counts.get(cat.id, 0) > 0:
            categories_with_products.add(cat.id)

    return HTMLResponse(_render("admin.html",
        request=request,
        user=user,
        product_count=product_count,
        category_count=category_count,
        open_tabs_count=open_tabs_count,
        sent_tabs_count=sent_tabs_count,
        products_with_cats=products_with_cats,
        categories=categories,
        tables=tables,
        active_count=active_count,
        inactive_count=inactive_count,
        category_names=category_names,
        category_counts=category_counts,
        price_overrides=price_overrides,
        override_product_ids=override_product_ids,
        override_prices=override_prices,
        category_product_counts=category_product_counts,
        categories_with_products=categories_with_products,
        sync_logs=sync_logs,
        shopify_mock=SHOPIFY_MOCK,
    ))


@app.post("/admin/sync-shopify")
async def admin_sync_shopify(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = get_current_user(request)
    if not user or not user.get("is_admin"):
        return RedirectResponse(url="/login", status_code=303)

    result = await sync_products()

    # Load categories for auto-matching
    cat_result = await db.execute(select(Category))
    categories = cat_result.scalars().all()

    added = 0
    updated = 0
    unchanged = 0

    if result["success"] and result["products"]:
        for sp in result["products"]:
            # Check if product exists by shopify_variant_id
            res = await db.execute(
                select(Product).where(Product.shopify_variant_id == sp["shopify_variant_id"])
            )
            existing = res.scalar_one_or_none()

            if existing:
                # Update price + name if changed, preserve is_active
                changed = False
                if float(existing.price) != sp["price"] or existing.name != sp["name"]:
                    existing.price = sp["price"]
                    existing.name = sp["name"]
                    changed = True
                # Auto-match category if missing
                if not existing.category_id:
                    cat_id = auto_match_category(
                        sp.get("name", ""),
                        sp.get("product_type", ""),
                        categories
                    )
                    if cat_id:
                        existing.category_id = cat_id
                        changed = True
                if changed:
                    updated += 1
                else:
                    unchanged += 1
                # Image matching by handle
                if not existing.image_path and sp.get("slug"):
                    handle = sp["slug"]
                    img_path = f"/static/images/products/{handle}.jpg"
                    import os as _os
                    full_path = f"/opt/tab-tracker/static/images/products/{handle}.jpg"
                    if _os.path.exists(full_path):
                        existing.image_path = img_path
            else:
                # New product - preserve is_active=False by default
                # (admin must explicitly enable via toggle)
                # Try to match image by handle
                img = sp.get("image_url")
                if sp.get("slug"):
                    import os as _os
                    local_img = f"/opt/tab-tracker/static/images/products/{sp['slug']}.jpg"
                    if _os.path.exists(local_img):
                        img = f"/static/images/products/{sp['slug']}.jpg"
                
                # Auto-match category
                cat_id = auto_match_category(
                    sp.get("name", ""),
                    sp.get("product_type", ""),
                    categories
                )
                
                new_product = Product(
                    name=sp["name"],
                    slug=sp.get("slug", ""),
                    price=sp["price"],
                    shopify_variant_id=sp["shopify_variant_id"],
                    shopify_product_id=sp["shopify_product_id"],
                    image_path=img,
                    category_id=cat_id,
                    is_active=False,
                )
                db.add(new_product)
                added += 1

        await db.commit()

    # Log sync
    log = SyncLog(
        synced_by=user["id"],
        products_added=added,
        products_updated=updated,
        products_unchanged=unchanged,
        status="success" if result["success"] else "error",
        message=result.get("message", ""),
    )
    db.add(log)
    await db.commit()

    return RedirectResponse(
        url=f"/admin?sync={'ok' if result['success'] else 'err'}",
        status_code=303,
    )


@app.post("/admin/products/{product_id}/toggle")
async def toggle_product(
    product_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = get_current_user(request)
    if not user or not user.get("is_admin"):
        return RedirectResponse(url="/login", status_code=303)

    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product:
        product.is_active = not product.is_active
        await db.commit()

    # AJAX: return JSON, no page reload
    is_ajax = request.headers.get("accept", "").startswith("application/json")
    if is_ajax:
        return JSONResponse({"ok": True, "product_id": product_id, "is_active": product.is_active if product else False})

    return RedirectResponse(url="/admin", status_code=303)


# ─── Product Category Assignment ───

@app.post("/admin/products/{product_id}/category")
async def set_product_category(
    product_id: int,
    request: Request,
    category_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = get_current_user(request)
    if not user or not user.get("is_admin"):
        return RedirectResponse(url="/login", status_code=303)

    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product:
        product.category_id = category_id if category_id > 0 else None
        await db.commit()

    # AJAX: return JSON, no page reload
    is_ajax = request.headers.get("accept", "").startswith("application/json")
    if is_ajax:
        cat_name = None
        if category_id > 0:
            cat_res = await db.execute(select(Category).where(Category.id == category_id))
            cat = cat_res.scalar_one_or_none()
            cat_name = cat.name if cat else None
        return JSONResponse({"ok": True, "product_id": product_id, "category_id": category_id, "category_name": cat_name})

    return RedirectResponse(url="/admin#products", status_code=303)


# ─── Category CRUD ───

@app.post("/admin/categories/add")
async def add_category(
    request: Request,
    name: str = Form(...),
    icon: str = Form("🍽️"),
    db: AsyncSession = Depends(get_db),
):
    user = get_current_user(request)
    if not user or not user.get("is_admin"):
        return RedirectResponse(url="/login", status_code=303)

    result = await db.execute(select(sql_func.max(Category.sort_order)))
    max_sort = result.scalar() or 0
    cat = Category(name=name, icon=icon, sort_order=max_sort + 1, is_active=True)
    db.add(cat)
    await db.commit()
    return RedirectResponse(url="/admin?tab=categories", status_code=303)


@app.post("/admin/categories/{category_id}/update")
async def update_category(
    category_id: int,
    request: Request,
    name: str = Form(...),
    icon: str = Form("🍽️"),
    db: AsyncSession = Depends(get_db),
):
    user = get_current_user(request)
    if not user or not user.get("is_admin"):
        return RedirectResponse(url="/login", status_code=303)

    result = await db.execute(select(Category).where(Category.id == category_id))
    cat = result.scalar_one_or_none()
    if cat:
        cat.name = name
        cat.icon = icon
        await db.commit()

    return RedirectResponse(url="/admin?tab=categories", status_code=303)


@app.post("/admin/categories/{category_id}/delete")
async def delete_category(
    category_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = get_current_user(request)
    if not user or not user.get("is_admin"):
        return RedirectResponse(url="/login", status_code=303)

    # Null out product references first
    result = await db.execute(select(Product).where(Product.category_id == category_id))
    for p in result.scalars().all():
        p.category_id = None
    # Delete category
    result = await db.execute(select(Category).where(Category.id == category_id))
    cat = result.scalar_one_or_none()
    if cat:
        await db.delete(cat)
        await db.commit()

    return RedirectResponse(url="/admin?tab=categories", status_code=303)


# ─── Auto-match categories on sync ───

def auto_match_category(product_name: str, product_type: str, categories: list) -> int | None:
    """Match a product to a category based on name/type keywords."""
    name_lower = (product_name or "").lower()
    type_lower = (product_type or "").lower()
    combined = f"{name_lower} {type_lower}"
    
    # Keyword → category name mapping
    rules = [
        ("alfajor", "Alfajores"),
        ("maicena", "Alfajores"),
        ("empanada", "Empanadas"),
        ("emp", "Empanadas"),
        ("medialuna", "Pastries and Facturas"),
        ("factura", "Pastries and Facturas"),
        ("cremona", "Pastries and Facturas"),
        ("cremonita", "Pastries and Facturas"),
        ("sweet bread", "Pastries and Facturas"),
        ("humita", "Empanadas"),
        ("brunch", "Boxes and Assortments"),
        ("poster", "Other"),
        ("king's day", "Drinks"),
        ("kings day", "Drinks"),
        ("cake", "Desserts"),
        ("pie", "Desserts"),
        ("overload", "Desserts"),
        ("churrinche", "Pastries and Facturas"),
        ("chipa", "Pastries and Facturas"),
        ("vigilante", "Pastries and Facturas"),
        ("tortita", "Pastries and Facturas"),
        ("pionono", "Pastries and Facturas"),
        ("bolleria", "Pastries and Facturas"),
        ("frambuesa", "Pastries and Facturas"),
        ("conito", "Pastries and Facturas"),
        ("berlinesa", "Pastries and Facturas"),
        ("arrollado", "Pastries and Facturas"),
        ("bandeja", "Pastries and Facturas"),
        ("masa", "Pastries and Facturas"),
        ("bebida", "Drinks"),
        ("coffee", "Drinks"),
        ("espresso", "Drinks"),
        ("cappuccino", "Drinks"),
        ("latte", "Drinks"),
        ("chai", "Drinks"),
        ("americano", "Drinks"),
        ("cortado", "Drinks"),
        ("iced", "Drinks"),
        ("tea", "Drinks"),
        ("chocolate", "Drinks"),
        ("coca", "Drinks"),
        ("fanta", "Drinks"),
        ("juice", "Drinks"),
        ("water", "Drinks"),
        ("kombucha", "Drinks"),
        ("soft drink", "Drinks"),
        ("ice cream", "Ice Cream"),
        ("helado", "Ice Cream"),
        ("postre", "Desserts"),
        ("tres leches", "Desserts"),
        ("chocotorta", "Desserts"),
        ("lemon pie", "Desserts"),
        ("lunch", "Lunch Deals"),
        ("pick box", "Boxes and Assortments"),
        ("gift", "Boxes and Assortments"),
        ("box", "Boxes and Assortments"),
        ("assortment", "Boxes and Assortments"),
        # Drinks - expanded
        ("americano", "Drinks"),
        ("flat white", "Drinks"),
        ("panna", "Drinks"),
        ("pellegrino", "Drinks"),
        ("acqua", "Drinks"),
        ("apple/ orange", "Drinks"),
        ("apple/orange", "Drinks"),
        ("coca", "Drinks"),
        ("fanta", "Drinks"),
        ("kombucha", "Drinks"),
        ("dash water", "Drinks"),
        ("clipper", "Drinks"),
        ("heineken", "Drinks"),
        (" oats", "Drinks"),
        ("coco milk", "Drinks"),
        ("hot water", "Drinks"),
        ("san pellegrino", "Drinks"),
        ("soft drink", "Drinks"),
        ("brewed", "Drinks"),
        ("matcha", "Drinks"),
        ("frappe", "Drinks"),
        # Ice cream - expanded
        ("helado", "Ice Cream"),
        ("truffel", "Ice Cream"),
        ("banana split ice", "Ice Cream"),
        ("hazelnut ice", "Ice Cream"),
        ("dulce de leche ice", "Ice Cream"),
        # Desserts - expanded
        ("apple pie", "Desserts"),
        ("arroz con leche", "Desserts"),
        ("cookies and cream", "Desserts"),
        ("chocotorta", "Desserts"),
        ("tres leches", "Desserts"),
        ("lemon", "Desserts"),
        # Pastries - expanded
        ("chocman", "Pastries and Facturas"),
        ("marroc", "Pastries and Facturas"),
        ("librito", "Pastries and Facturas"),
        ("colaciones", "Pastries and Facturas"),
        ("conito", "Pastries and Facturas"),
        ("masas", "Pastries and Facturas"),
        # Alfajores - expanded
        ("alfajor", "Alfajores"),
        ("alf oost", "Alfajores"),
        (" alf ", "Alfajores"),
        # Empanadas - expanded
        ("empanada", "Empanadas"),
        ("locro", "Empanadas"),
        ("choripan", "Empanadas"),
        # Lunch
        ("lunch deal", "Lunch Deals"),
        ("lunch deal + drink", "Lunch Deals"),
    ]
    
    cat_names = {c.name.lower(): c.id for c in categories if c.name}
    
    for keyword, cat_name in rules:
        if keyword in combined:
            # Find matching category (case-insensitive)
            for cn, cid in cat_names.items():
                if cat_name.lower() in cn or cn in cat_name.lower():
                    return cid
    return None


# ─── Price Override (Translation Rules) ───

@app.post("/admin/overrides/add")
async def add_override(
    request: Request,
    product_id: int = Form(...),
    override_price: float = Form(...),
    checkout_variant_id: str = Form("..."),
    checkout_product_name: str = Form("..."),
    rule_name: str = Form("..."),
    apply_to_matching: str = Form("..."),
    db: AsyncSession = Depends(get_db),
):
    user = get_current_user(request)
    if not user or not user.get("is_admin"):
        return RedirectResponse(url="/login", status_code=303)

    if apply_to_matching == "on":
        # Apply to all products matching the same Shopify price
        source_result = await db.execute(select(Product).where(Product.id == product_id))
        source = source_result.scalar_one_or_none()
        if source:
            from decimal import Decimal as D
            result = await db.execute(
                select(Product).where(Product.price == source.price, Product.is_active == True)
            )
            matching = result.scalars().all()
            for p in matching:
                existing = await db.execute(
                    select(PriceOverride).where(PriceOverride.product_id == p.id)
                )
                if not existing.scalar_one_or_none():
                    db.add(PriceOverride(
                        product_id=p.id,
                        override_price=D(str(override_price)),
                        checkout_variant_id=checkout_variant_id or None,
                        checkout_product_name=checkout_product_name or None,
                        rule_name=rule_name or None,
                        is_active=True,
                    ))
    else:
        from decimal import Decimal as D
        # Remove existing override for this product if any
        result = await db.execute(
            select(PriceOverride).where(PriceOverride.product_id == product_id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.override_price = D(str(override_price))
            existing.checkout_variant_id = checkout_variant_id or None
            existing.checkout_product_name = checkout_product_name or None
            existing.rule_name = rule_name or None
            existing.is_active = True
        else:
            db.add(PriceOverride(
                product_id=product_id,
                override_price=D(str(override_price)),
                checkout_variant_id=checkout_variant_id or None,
                checkout_product_name=checkout_product_name or None,
                rule_name=rule_name or None,
                is_active=True,
            ))

    await db.commit()
    return RedirectResponse(url="/admin?tab=rules", status_code=303)


@app.post("/admin/overrides/{override_id}/delete")
async def delete_override(
    override_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = get_current_user(request)
    if not user or not user.get("is_admin"):
        return RedirectResponse(url="/login", status_code=303)

    result = await db.execute(select(PriceOverride).where(PriceOverride.id == override_id))
    override = result.scalar_one_or_none()
    if override:
        await db.delete(override)
        await db.commit()

    return RedirectResponse(url="/admin?tab=rules", status_code=303)


@app.post("/admin/overrides/{override_id}/toggle")
async def toggle_override(
    override_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = get_current_user(request)
    if not user or not user.get("is_admin"):
        return RedirectResponse(url="/login", status_code=303)

    result = await db.execute(select(PriceOverride).where(PriceOverride.id == override_id))
    override = result.scalar_one_or_none()
    if override:
        override.is_active = not override.is_active
        await db.commit()

    return RedirectResponse(url="/admin?tab=rules", status_code=303)


@app.post("/admin/products/{product_id}/price")
async def update_price(
    product_id: int,
    request: Request,
    price: float = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = get_current_user(request)
    if not user or not user.get("is_admin"):
        return RedirectResponse(url="/login", status_code=303)

    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product:
        product.price = Decimal(str(price))
        await db.commit()

    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/tables/add")
async def add_table(
    request: Request,
    name: str = Form(...),
    seats: int = Form(4),
    db: AsyncSession = Depends(get_db),
):
    user = get_current_user(request)
    if not user or not user.get("is_admin"):
        return RedirectResponse(url="/login", status_code=303)

    result = await db.execute(select(Shop).where(Shop.has_tables == True))
    shop = result.scalar_one_or_none()
    if shop:
        table = Table(shop_id=shop.id, name=name, seats=seats, sort_order=0)
        db.add(table)
        await db.commit()

    return RedirectResponse(url="/admin", status_code=303)


async def _render_bill(tab_id: int, db: AsyncSession) -> HTMLResponse:
    """Helper to render the bill partial for HTMX responses."""
    result = await db.execute(select(TabItem).where(TabItem.tab_id == tab_id).order_by(TabItem.added_at))
    items = result.scalars().all()
    total = sum(float(item.unit_price) * item.quantity for item in items)

    return HTMLResponse(_render("partials/bill.html",
        tab_id=tab_id,
        items=items,
        total=total,
    ))




# ─── Transaction History + API + CSV Export ───

async def _check_api_key(request: Request) -> bool:
    """Check for valid API key in header or query param."""
    key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    return key == TRANSACTION_API_KEY


@app.get("/history", response_class=HTMLResponse)
async def history_page(
    request: Request,
    page: int = Query(1, ge=1),
    from_date: str = Query(None),
    to_date: str = Query(None),
    status: str = Query(None),
    table_id: int = Query(None),
    db: AsyncSession = Depends(get_db),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    per_page = 25
    offset = (page - 1) * per_page

    # Build query with filters
    conditions = []
    if from_date:
        from_dt = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        conditions.append(Transaction.sent_at >= from_dt)
    if to_date:
        to_dt = datetime.strptime(to_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        conditions.append(Transaction.sent_at <= to_dt)
    if status:
        conditions.append(Transaction.shopify_status == status)
    if table_id:
        conditions.append(Transaction.table_id == table_id)

    where_clause = and_(*conditions) if conditions else True

    # Get total count
    count_q = select(sql_func.count()).select_from(Transaction)
    for c in conditions:
        count_q = count_q.where(c)
    count_result = await db.execute(count_q)
    total_count = count_result.scalar()

    # Get paginated transactions
    tx_q = select(Transaction).order_by(Transaction.sent_at.desc()).offset(offset).limit(per_page)
    for c in conditions:
        tx_q = tx_q.where(c)
    tx_result = await db.execute(tx_q)
    transactions = tx_result.scalars().all()

    # Load items for each transaction
    for tx in transactions:
        items_res = await db.execute(
            select(TransactionItem)
            .where(TransactionItem.transaction_id == tx.id)
            .order_by(TransactionItem.sort_order)
        )
        tx.items = items_res.scalars().all()

    # Summary stats (with same filters)
    sum_q = select(
        sql_func.coalesce(sql_func.sum(Transaction.total_amount), 0),
        sql_func.coalesce(sql_func.sum(Transaction.item_count), 0),
    )
    for c in conditions:
        sum_q = sum_q.where(c)
    sum_result = await db.execute(sum_q)
    total_revenue, total_items = sum_result.fetchone()

    avg_tx = float(total_revenue) / total_count if total_count > 0 else 0

    # Get all tables for filter dropdown
    tables_res = await db.execute(select(Table).order_by(Table.sort_order, Table.name))
    all_tables = tables_res.scalars().all()

    total_pages = max(1, (total_count + per_page - 1) // per_page)

    return HTMLResponse(_render("history.html",
        request=request,
        user=user,
        transactions=transactions,
        total_transactions=total_count,
        total_revenue=float(total_revenue),
        total_items=int(total_items),
        avg_transaction=avg_tx,
        page=page,
        total_pages=total_pages,
        from_date=from_date,
        to_date=to_date,
        status_filter=status,
        table_filter=table_id,
        all_tables=all_tables,
    ))


@app.get("/api/v1/transactions/{tx_id}")
async def api_get_transaction(
    tx_id: int,
    auth: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Transaction).where(Transaction.id == tx_id))
    tx = result.scalar_one_or_none()
    if not tx:
        return JSONResponse({"error": "Transaction not found"}, status_code=404)

    items_res = await db.execute(
        select(TransactionItem)
        .where(TransactionItem.transaction_id == tx.id)
        .order_by(TransactionItem.sort_order)
    )
    items = items_res.scalars().all()

    return JSONResponse({
        "id": tx.id,
        "table": tx.table_name,
        "shop": tx.shop_name,
        "cashier": tx.cashier_name,
        "guests": tx.guest_count,
        "total": float(tx.total_amount),
        "currency": tx.currency,
        "item_count": tx.item_count,
        "status": tx.shopify_status,
        "shopify_draft_order_id": tx.shopify_draft_order_id,
        "pos_order_id": tx.pos_order_id,
        "pos_terminal_id": tx.pos_terminal_id,
        "checkout_method": tx.checkout_method,
        "opened_at": tx.opened_at.isoformat() if tx.opened_at else None,
        "sent_at": tx.sent_at.isoformat() if tx.sent_at else None,
        "completed_at": tx.completed_at.isoformat() if tx.completed_at else None,
        "items": [{
            "product_name": item.product_name,
            "checkout_name": item.checkout_name,
            "flavor": item.flavor,
            "unit_price": float(item.unit_price),
            "quantity": item.quantity,
            "line_total": float(item.line_total),
            "shopify_variant_id": item.shopify_variant_id,
        } for item in items],
    })


@app.get("/api/v1/transactions")
async def api_list_transactions(
    auth: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    from_date: str = Query(None),
    to_date: str = Query(None),
    status: str = Query(None),
    table_id: int = Query(None),
    checkout_method: str = Query(None),
):
    offset = (page - 1) * per_page
    conditions = []
    if from_date:
        from_dt = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        conditions.append(Transaction.sent_at >= from_dt)
    if to_date:
        to_dt = datetime.strptime(to_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        conditions.append(Transaction.sent_at <= to_dt)
    if status:
        conditions.append(Transaction.shopify_status == status)
    if table_id:
        conditions.append(Transaction.table_id == table_id)
    if checkout_method:
        conditions.append(Transaction.checkout_method == checkout_method)

    # Count
    count_q = select(sql_func.count()).select_from(Transaction)
    for c in conditions:
        count_q = count_q.where(c)
    total = (await db.execute(count_q)).scalar()

    # Query
    tx_q = select(Transaction).order_by(Transaction.sent_at.desc()).offset(offset).limit(per_page)
    for c in conditions:
        tx_q = tx_q.where(c)
    txs = (await db.execute(tx_q)).scalars().all()

    # Load items
    result_txs = []
    for tx in txs:
        items_res = await db.execute(
            select(TransactionItem)
            .where(TransactionItem.transaction_id == tx.id)
            .order_by(TransactionItem.sort_order)
        )
        items = items_res.scalars().all()
        result_txs.append({
            "id": tx.id,
            "table": tx.table_name,
            "shop": tx.shop_name,
            "cashier": tx.cashier_name,
            "guests": tx.guest_count,
            "total": float(tx.total_amount),
            "currency": tx.currency,
            "item_count": tx.item_count,
            "status": tx.shopify_status,
            "shopify_draft_order_id": tx.shopify_draft_order_id,
            "pos_order_id": tx.pos_order_id,
            "pos_terminal_id": tx.pos_terminal_id,
            "checkout_method": tx.checkout_method,
            "opened_at": tx.opened_at.isoformat() if tx.opened_at else None,
            "sent_at": tx.sent_at.isoformat() if tx.sent_at else None,
            "completed_at": tx.completed_at.isoformat() if tx.completed_at else None,
            "items": [{
                "product_name": item.product_name,
                "checkout_name": item.checkout_name,
                "flavor": item.flavor,
                "unit_price": float(item.unit_price),
                "quantity": item.quantity,
                "line_total": float(item.line_total),
            } for item in items],
        })

    return JSONResponse({
        "transactions": result_txs,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    })


@app.get("/exports/transactions.csv")
async def export_csv(
    request: Request,
    db: AsyncSession = Depends(get_db),
    from_date: str = Query(None),
    to_date: str = Query(None),
    status: str = Query(None),
):
    """CSV export of all transactions with line items."""
    # Allow both logged-in users and API key
    user = get_current_user(request)
    if not user and not await _check_api_key(request):
        return JSONResponse({"error": "Authentication required"}, status_code=401)

    conditions = []
    if from_date:
        from_dt = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        conditions.append(Transaction.sent_at >= from_dt)
    if to_date:
        to_dt = datetime.strptime(to_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        conditions.append(Transaction.sent_at <= to_dt)
    if status:
        conditions.append(Transaction.shopify_status == status)

    tx_q = select(Transaction).order_by(Transaction.sent_at.desc())
    for c in conditions:
        tx_q = tx_q.where(c)
    txs = (await db.execute(tx_q)).scalars().all()

    import csv, io
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "transaction_id", "sent_at", "opened_at", "table", "shop", "cashier",
        "guests", "status", "shopify_draft_order_id",
        "item_product_name", "item_checkout_name", "item_flavor",
        "item_unit_price", "item_quantity", "item_line_total",
        "transaction_total",
    ])

    for tx in txs:
        items_res = await db.execute(
            select(TransactionItem)
            .where(TransactionItem.transaction_id == tx.id)
            .order_by(TransactionItem.sort_order)
        )
        items = items_res.scalars().all()

        for item in items:
            writer.writerow([
                tx.id,
                tx.sent_at.isoformat() if tx.sent_at else "",
                tx.opened_at.isoformat() if tx.opened_at else "",
                tx.table_name or "",
                tx.shop_name or "",
                tx.cashier_name or "",
                tx.guest_count or "",
                tx.shopify_status or "",
                tx.shopify_draft_order_id or "",
                item.product_name,
                item.checkout_name or "",
                item.flavor or "",
                float(item.unit_price),
                item.quantity,
                float(item.line_total),
                float(tx.total_amount),
            ])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions_export.csv"},
    )


# ═══════════════════════════════════════════════════
# POS Extension API — /api/v1/* endpoints
# All protected by verify_api_key dependency.
# ═══════════════════════════════════════════════════

from pydantic import BaseModel

# ─── Request schemas ───

class OpenTabRequest(BaseModel):
    table_id: int
    pos_terminal_id: str | None = None
    staff_id: str | None = None
    guests: int = 1
    notes: str | None = None

class AddItemRequest(BaseModel):
    product_id: int

class UpdateItemQtyRequest(BaseModel):
    quantity: int

class CloseTabRequest(BaseModel):
    pos_terminal_id: str | None = None
    staff_id: str | None = None


# ─── Products ───

@app.get("/api/v1/products")
async def api_v1_products(
    auth: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Return all active products with category name and active price override info."""
    result = await db.execute(
        select(Product, Category)
        .outerjoin(Category, Product.category_id == Category.id)
        .where(Product.is_active == True)
        .order_by(Category.sort_order, Product.sort_order, Product.name)
    )
    rows = result.all()

    # Load active price overrides
    ov_result = await db.execute(
        select(PriceOverride).where(PriceOverride.is_active == True)
    )
    overrides = {o.product_id: o for o in ov_result.scalars().all()}

    products = []
    for product, category in rows:
        ov = overrides.get(product.id)
        products.append({
            "id": product.id,
            "name": product.name,
            "slug": product.slug,
            "price": float(product.price),
            "currency": product.currency,
            "category_id": product.category_id,
            "category_name": category.name if category else None,
            "shopify_variant_id": product.shopify_variant_id,
            "shopify_product_id": product.shopify_product_id,
            "image_path": product.image_path,
            "override_price": float(ov.override_price) if ov else None,
            "is_active": product.is_active,
        })

    return JSONResponse(products)


@app.get("/api/v1/categories")
async def api_v1_categories(
    auth: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Return all active categories ordered by sort_order."""
    result = await db.execute(
        select(Category)
        .where(Category.is_active == True)
        .order_by(Category.sort_order, Category.name)
    )
    categories = result.scalars().all()

    return JSONResponse([
        {
            "id": cat.id,
            "name": cat.name,
            "icon": cat.icon,
            "sort_order": cat.sort_order,
            "is_active": cat.is_active,
        }
        for cat in categories
    ])


# ─── Tables ───

@app.get("/api/v1/tables")
async def api_v1_tables(
    auth: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Return all active tables for the current shop."""
    shop_id = auth.get("shop_id")
    if not shop_id:
        return JSONResponse([])

    result = await db.execute(
        select(Table)
        .where(Table.shop_id == shop_id, Table.is_active == True)
        .order_by(Table.sort_order, Table.name)
    )
    tables = result.scalars().all()

    return JSONResponse([
        {
            "id": t.id,
            "name": t.name,
            "seats": t.seats,
            "sort_order": t.sort_order,
            "is_active": t.is_active,
        }
        for t in tables
    ])


# ─── Tabs CRUD ───

@app.get("/api/v1/tabs/open")
async def api_v1_tabs_open(
    auth: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Return all open tabs across all tables."""
    shop_id = auth.get("shop_id")
    if not shop_id:
        return JSONResponse([])

    result = await db.execute(
        select(Tab, Table)
        .join(Table, Tab.table_id == Table.id)
        .where(Tab.shop_id == shop_id, Tab.status == "open")
        .order_by(Tab.opened_at.desc())
    )
    rows = result.all()

    results = []
    for tab, table in rows:
        items_res = await db.execute(
            select(TabItem).where(TabItem.tab_id == tab.id).order_by(TabItem.added_at)
        )
        items = items_res.scalars().all()
        total = sum(float(i.unit_price) * i.quantity for i in items)
        item_count = sum(i.quantity for i in items)

        results.append({
            "id": tab.id,
            "table_id": tab.table_id,
            "table_name": table.name,
            "status": tab.status,
            "guests": tab.guests,
            "item_count": item_count,
            "total": round(total, 2),
            "opened_at": tab.opened_at.isoformat() if tab.opened_at else None,
            "notes": tab.notes,
            "items": [
                {
                    "id": i.id,
                    "product_id": i.product_id,
                    "product_name": i.product_name,
                    "unit_price": float(i.unit_price),
                    "quantity": i.quantity,
                    "added_at": i.added_at.isoformat() if i.added_at else None,
                }
                for i in items
            ],
        })

    return JSONResponse(results)


@app.get("/api/v1/tabs")
async def api_v1_get_tab(
    table_id: int = Query(...),
    auth: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Return the open tab + items for a specific table."""
    shop_id = auth.get("shop_id")
    if not shop_id:
        return JSONResponse({"error": "No shop configured"}, status_code=400)

    result = await db.execute(
        select(Tab)
        .where(Tab.table_id == table_id, Tab.shop_id == shop_id, Tab.status == "open")
    )
    tab = result.scalar_one_or_none()
    if not tab:
        return JSONResponse({"tab": None, "items": []})

    items_res = await db.execute(
        select(TabItem).where(TabItem.tab_id == tab.id).order_by(TabItem.added_at)
    )
    items = items_res.scalars().all()
    total = sum(float(i.unit_price) * i.quantity for i in items)

    return JSONResponse({
        "tab": {
            "id": tab.id,
            "table_id": tab.table_id,
            "status": tab.status,
            "guests": tab.guests,
            "opened_at": tab.opened_at.isoformat() if tab.opened_at else None,
            "closed_at": tab.closed_at.isoformat() if tab.closed_at else None,
            "pos_cart_sent_at": tab.pos_cart_sent_at.isoformat() if tab.pos_cart_sent_at else None,
            "pos_terminal_id": tab.pos_terminal_id,
            "notes": tab.notes,
        },
        "items": [
            {
                "id": i.id,
                "product_id": i.product_id,
                "product_name": i.product_name,
                "unit_price": float(i.unit_price),
                "quantity": i.quantity,
                "added_at": i.added_at.isoformat() if i.added_at else None,
            }
            for i in items
        ],
        "total": round(total, 2),
    })


@app.post("/api/v1/tabs", status_code=201)
async def api_v1_open_tab(
    body: OpenTabRequest,
    auth: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Open a new tab for a table. Creates a pos_sessions row tracking the terminal."""
    shop_id = auth.get("shop_id")
    if not shop_id:
        raise HTTPException(status_code=400, detail="No shop configured")

    # Verify table exists and belongs to this shop
    result = await db.execute(
        select(Table).where(Table.id == body.table_id, Table.shop_id == shop_id)
    )
    table = result.scalar_one_or_none()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")

    # Check no open tab already exists for this table
    result = await db.execute(
        select(Tab).where(
            Tab.table_id == body.table_id,
            Tab.shop_id == shop_id,
            Tab.status == "open",
        )
    )
    existing_tab = result.scalar_one_or_none()
    if existing_tab:
        raise HTTPException(status_code=409, detail="Table already has an open tab")

    # Create tab
    tab = Tab(
        table_id=body.table_id,
        shop_id=shop_id,
        status="open",
        guests=body.guests,
        notes=body.notes or None,
        pos_terminal_id=body.pos_terminal_id,
    )
    db.add(tab)
    await db.flush()

    # Create pos_sessions row
    session = PosSession(
        shop_id=shop_id,
        pos_terminal_id=body.pos_terminal_id,
        staff_id=body.staff_id,
        opened_tab_ids=[tab.id],
    )
    db.add(session)
    await db.commit()
    await db.refresh(tab)

    return JSONResponse({
        "id": tab.id,
        "table_id": tab.table_id,
        "status": tab.status,
        "guests": tab.guests,
        "opened_at": tab.opened_at.isoformat() if tab.opened_at else None,
        "pos_session_id": session.id,
    }, status_code=201)


@app.post("/api/v1/tabs/{tab_id}/items", status_code=201)
async def api_v1_add_item(
    tab_id: int,
    body: AddItemRequest,
    auth: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Add an item to a tab. Merges with existing line of same product + price."""
    # Verify tab exists and is open
    result = await db.execute(select(Tab).where(Tab.id == tab_id, Tab.status == "open"))
    tab = result.scalar_one_or_none()
    if not tab:
        raise HTTPException(status_code=404, detail="Tab not found or not open")

    # Get product
    result = await db.execute(select(Product).where(Product.id == body.product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Check for price override
    ov_result = await db.execute(
        select(PriceOverride).where(
            PriceOverride.product_id == body.product_id,
            PriceOverride.is_active == True,
        )
    )
    override = ov_result.scalar_one_or_none()
    unit_price = override.override_price if override else product.price

    # Merge with existing line item of same product AND same price
    existing_res = await db.execute(
        select(TabItem).where(
            TabItem.tab_id == tab_id,
            TabItem.product_id == body.product_id,
            TabItem.unit_price == unit_price,
        )
    )
    existing = existing_res.scalar_one_or_none()

    if existing:
        existing.quantity += 1
    else:
        item = TabItem(
            tab_id=tab_id,
            product_id=body.product_id,
            product_name=product.name,
            unit_price=unit_price,
            quantity=1,
        )
        db.add(item)

    await db.commit()

    # Return updated items list
    items_res = await db.execute(
        select(TabItem).where(TabItem.tab_id == tab_id).order_by(TabItem.added_at)
    )
    items = items_res.scalars().all()
    total = sum(float(i.unit_price) * i.quantity for i in items)

    return JSONResponse({
        "items": [
            {
                "id": i.id,
                "product_id": i.product_id,
                "product_name": i.product_name,
                "unit_price": float(i.unit_price),
                "quantity": i.quantity,
                "added_at": i.added_at.isoformat() if i.added_at else None,
            }
            for i in items
        ],
        "total": round(total, 2),
    }, status_code=201)


@app.delete("/api/v1/tabs/{tab_id}/items/{item_id}")
async def api_v1_delete_item(
    tab_id: int,
    item_id: int,
    auth: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Remove an item from a tab."""
    result = await db.execute(
        select(TabItem).where(TabItem.id == item_id, TabItem.tab_id == tab_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    await db.delete(item)
    await db.commit()

    # Return updated items list
    items_res = await db.execute(
        select(TabItem).where(TabItem.tab_id == tab_id).order_by(TabItem.added_at)
    )
    items = items_res.scalars().all()
    total = sum(float(i.unit_price) * i.quantity for i in items)

    return JSONResponse({
        "items": [
            {
                "id": i.id,
                "product_id": i.product_id,
                "product_name": i.product_name,
                "unit_price": float(i.unit_price),
                "quantity": i.quantity,
            }
            for i in items
        ],
        "total": round(total, 2),
    })


@app.patch("/api/v1/tabs/{tab_id}/items/{item_id}")
async def api_v1_update_item_qty(
    tab_id: int,
    item_id: int,
    body: UpdateItemQtyRequest,
    auth: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Update item quantity. If quantity <= 0, removes the item."""
    result = await db.execute(
        select(TabItem).where(TabItem.id == item_id, TabItem.tab_id == tab_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if body.quantity <= 0:
        await db.delete(item)
    else:
        item.quantity = body.quantity

    await db.commit()

    # Return updated items list
    items_res = await db.execute(
        select(TabItem).where(TabItem.tab_id == tab_id).order_by(TabItem.added_at)
    )
    items = items_res.scalars().all()
    total = sum(float(i.unit_price) * i.quantity for i in items)

    return JSONResponse({
        "items": [
            {
                "id": i.id,
                "product_id": i.product_id,
                "product_name": i.product_name,
                "unit_price": float(i.unit_price),
                "quantity": i.quantity,
            }
            for i in items
        ],
        "total": round(total, 2),
    })


@app.post("/api/v1/tabs/{tab_id}/close")
async def api_v1_close_tab(
    tab_id: int,
    body: CloseTabRequest | None = None,
    auth: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Close a tab (after POS checkout completes)."""
    result = await db.execute(select(Tab).where(Tab.id == tab_id))
    tab = result.scalar_one_or_none()
    if not tab:
        raise HTTPException(status_code=404, detail="Tab not found")

    if tab.status == "closed":
        raise HTTPException(status_code=400, detail="Tab already closed")

    tab.status = "closed"
    tab.closed_at = datetime.now(timezone.utc)
    if body and body.pos_terminal_id:
        tab.pos_terminal_id = body.pos_terminal_id

    await db.commit()

    return JSONResponse({
        "id": tab.id,
        "table_id": tab.table_id,
        "status": tab.status,
        "closed_at": tab.closed_at.isoformat() if tab.closed_at else None,
    })


# ─── Send to Cart ───

class SendToCartRequest(BaseModel):
    pos_terminal_id: str | None = None
    staff_id: str | None = None


@app.post("/api/v1/tabs/{tab_id}/send-to-cart")
async def api_v1_send_to_cart(
    tab_id: int,
    body: SendToCartRequest | None = None,
    auth: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Record a tab as sent to the POS cart.
    Creates a Transaction record (does NOT call Shopify — that's client-side).
    """
    # Get tab + items
    result = await db.execute(select(Tab).where(Tab.id == tab_id))
    tab = result.scalar_one_or_none()
    if not tab:
        raise HTTPException(status_code=404, detail="Tab not found")

    # Prevent double-send
    if tab.status == "sent":
        raise HTTPException(status_code=400, detail="Tab already sent")
    if tab.status == "closed":
        raise HTTPException(status_code=400, detail="Tab is closed")

    result = await db.execute(
        select(TabItem).where(TabItem.tab_id == tab_id).order_by(TabItem.added_at)
    )
    items = result.scalars().all()

    if not items:
        raise HTTPException(status_code=400, detail="Cannot send empty tab")

    # Calculate totals
    total = sum(float(item.unit_price) * item.quantity for item in items)
    item_count = sum(item.quantity for item in items)

    # Get table name
    table_name = None
    table_id = None
    if tab.table_id:
        tbl_res = await db.execute(select(Table).where(Table.id == tab.table_id))
        tbl = tbl_res.scalar_one_or_none()
        if tbl:
            table_name = tbl.name
            table_id = tbl.id

    # Get shop name
    shop_name = None
    shop_res = await db.execute(select(Shop).where(Shop.id == tab.shop_id))
    shop_obj = shop_res.scalar_one_or_none()
    if shop_obj:
        shop_name = shop_obj.name

    pos_terminal_id = body.pos_terminal_id if body else None

    # Build and persist transaction
    from decimal import Decimal as D

    tx = Transaction(
        tab_id=tab.id,
        table_id=table_id,
        table_name=table_name,
        shop_id=tab.shop_id,
        shop_name=shop_name,
        guest_count=tab.guests,
        total_amount=D(str(round(total, 2))),
        currency="EUR",
        item_count=item_count,
        checkout_method="pos_extension",
        pos_terminal_id=pos_terminal_id,
        opened_at=tab.opened_at,
        sent_at=datetime.now(timezone.utc),
        notes=tab.notes,
    )
    db.add(tx)
    await db.flush()  # get tx.id

    # Snapshot line items
    for idx, item in enumerate(items):
        # Get product for variant ID and override info
        product = None
        if item.product_id:
            pres = await db.execute(select(Product).where(Product.id == item.product_id))
            product = pres.scalar_one_or_none()

        checkout_variant = product.shopify_variant_id if product else None
        checkout_name = item.product_name
        flavor_note = None

        if product:
            ov_res = await db.execute(
                select(PriceOverride).where(
                    PriceOverride.product_id == product.id,
                    PriceOverride.is_active == True,
                )
            )
            ov = ov_res.scalar_one_or_none()
            if ov:
                if ov.checkout_variant_id:
                    checkout_variant = ov.checkout_variant_id
                if ov.checkout_product_name:
                    checkout_name = ov.checkout_product_name
                if checkout_name != item.product_name:
                    flavor_note = item.product_name

        line_total = D(str(item.unit_price)) * item.quantity
        tx_item = TransactionItem(
            transaction_id=tx.id,
            product_id=item.product_id,
            product_name=item.product_name,
            checkout_name=checkout_name,
            unit_price=D(str(item.unit_price)),
            quantity=item.quantity,
            line_total=line_total,
            flavor=flavor_note,
            shopify_variant_id=checkout_variant,
            sort_order=idx,
        )
        db.add(tx_item)

    # Update tab status
    tab.status = "sent"
    tab.pos_cart_sent_at = datetime.now(timezone.utc)
    if pos_terminal_id:
        tab.pos_terminal_id = pos_terminal_id

    await db.commit()

    return JSONResponse({
        "transaction_id": tx.id,
        "tab_id": tab.id,
        "status": tab.status,
        "total": round(total, 2),
        "item_count": item_count,
    })



# ─── Startup ───

@app.on_event("startup")
async def startup():
    logger.info("Tab Tracker starting up...")
    logger.info(f"Shopify mock mode: {SHOPIFY_MOCK}")
