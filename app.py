"""
Tab Tracker — FastAPI main app.
Tablet-optimized restaurant tab tracking for Amsterdam Baking Company.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from decimal import Decimal

from fastapi import FastAPI, Request, Depends, HTTPException, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select, func as sql_func, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from config import SECRET_KEY, SESSION_COOKIE_NAME, SHOPIFY_MOCK
from database import get_db, engine, Base
from models import User, Shop, Table, Category, Product, Tab, TabItem, SyncLog
from auth import hash_password, verify_password, get_current_user
from shopify import create_draft_order, sync_products
from jinja import _render

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
logger = logging.getLogger("tabtracker")

app = FastAPI(title="Tab Tracker")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, session_cookie=SESSION_COOKIE_NAME)

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

    # Check for existing line item with same product
    result = await db.execute(
        select(TabItem).where(TabItem.tab_id == tab_id, TabItem.product_id == product_id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.quantity += 1
    else:
        item = TabItem(
            tab_id=tab_id,
            product_id=product_id,
            product_name=product.name,
            unit_price=product.price,
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

        shopify_items.append({
            "product_name": item.product_name,
            "quantity": item.quantity,
            "unit_price": float(item.unit_price),
            "shopify_variant_id": product.shopify_variant_id if product else None,
        })
        total += float(item.unit_price) * item.quantity

    # Call Shopify
    result = await create_draft_order(tab_id, shopify_items, total)

    if result["success"]:
        tab.status = "sent"
        tab.shopify_draft_order_id = result["draft_order_id"]
        tab.sent_at = datetime.now(timezone.utc)
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
            f'<p class="success-instruction">Switch to Shopify tab to complete checkout</p>'
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
                # Update price if changed
                if float(existing.price) != sp["price"]:
                    existing.price = sp["price"]
                    existing.name = sp["name"]
                    updated += 1
                else:
                    unchanged += 1
            else:
                # Create new product (uncategorized for now)
                new_product = Product(
                    name=sp["name"],
                    slug=sp.get("slug", ""),
                    price=sp["price"],
                    shopify_variant_id=sp["shopify_variant_id"],
                    shopify_product_id=sp["shopify_product_id"],
                    image_path=sp.get("image_url"),
                    is_active=True,
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

    return RedirectResponse(url="/admin", status_code=303)


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


# ─── Startup ───

@app.on_event("startup")
async def startup():
    logger.info("Tab Tracker starting up...")
    logger.info(f"Shopify mock mode: {SHOPIFY_MOCK}")
