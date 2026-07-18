"""
Shopify integration layer.
- Mock mode: simulates draft order creation, returns fake order ID
- Real mode: calls Shopify Admin API to create draft orders tagged as POS sale

When SHOPIFY_MOCK=true, all operations are simulated.
To go live: set SHOPIFY_STORE_DOMAIN, SHOPIFY_ADMIN_TOKEN, SHOPIFY_LOCATION_ID
and SHOPIFY_MOCK=false in the environment.
"""
import json
import logging
from datetime import datetime
from config import (
    SHOPIFY_STORE_DOMAIN,
    SHOPIFY_ADMIN_TOKEN,
    SHOPIFY_LOCATION_ID,
    SHOPIFY_MOCK,
)

logger = logging.getLogger("tabtracker.shopify")


async def create_draft_order(tab_id: int, items: list[dict], total: float) -> dict:
    """
    Create a Shopify Draft Order from a tab's items.

    Args:
        tab_id: Our internal tab ID
        items: List of {"product_name": str, "quantity": int, "unit_price": float, "shopify_variant_id": str|None}
        total: Total amount

    Returns:
        {"success": bool, "draft_order_id": str, "admin_url": str, "error": str|None}
    """
    if SHOPIFY_MOCK or not SHOPIFY_ADMIN_TOKEN:
        # Mock: generate a fake but realistic-looking response
        fake_id = f"gid://shopify/DraftOrder/{10_000_000 + tab_id}"
        logger.info(f"[MOCK] Draft order created for tab {tab_id}, total {total:.2f} EUR, {len(items)} line items")
        return {
            "success": True,
            "draft_order_id": fake_id,
            "admin_url": f"https://{SHOPIFY_STORE_DOMAIN or 'mock-store'}.myshopify.com/admin/draft_orders/{10_000_000 + tab_id}",
            "error": None,
            "mock": True,
        }

    # Real Shopify Admin API call
    import httpx

    line_items = []
    for item in items:
        line_item = {
            "quantity": item["quantity"],
            "title": item["product_name"],
            "price": str(item["unit_price"]),
        }
        if item.get("shopify_variant_id"):
            line_item["variant_id"] = item["shopify_variant_id"]
        line_items.append(line_item)

    payload = {
        "draft_order": {
            "line_items": line_items,
            "tags": "POS, in-store, tab-tracker",
            "note": f"Tab #{tab_id} - Created by Tab Tracker",
            "inventory_location_id": SHOPIFY_LOCATION_ID if SHOPIFY_LOCATION_ID else None,
        }
    }

    url = f"https://{SHOPIFY_STORE_DOMAIN}/admin/api/2024-10/draft_orders.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_ADMIN_TOKEN,
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=headers)
            data = resp.json()

            if resp.status_code == 201:
                order = data["draft_order"]
                logger.info(f"Draft order {order['id']} created for tab {tab_id}")
                return {
                    "success": True,
                    "draft_order_id": order["id"],
                    "admin_url": f"https://{SHOPIFY_STORE_DOMAIN}/admin/draft_orders/{order['id']}",
                    "error": None,
                    "mock": False,
                }
            else:
                logger.error(f"Shopify API error: {resp.status_code} {data}")
                return {
                    "success": False,
                    "draft_order_id": None,
                    "admin_url": None,
                    "error": f"Shopify API: {data.get('errors', str(resp.status_code))}",
                    "mock": False,
                }
    except Exception as e:
        logger.error(f"Shopify request failed: {e}")
        return {
            "success": False,
            "draft_order_id": None,
            "admin_url": None,
            "error": str(e),
            "mock": False,
        }


async def sync_products() -> dict:
    """
    Sync products from Shopify Admin API.
    Returns list of products with variant IDs, prices, images.

    In mock mode, returns empty list (use seed data instead).
    """
    if SHOPIFY_MOCK or not SHOPIFY_ADMIN_TOKEN:
        logger.info("[MOCK] Product sync requested — returning empty (use seed data)")
        return {
            "success": True,
            "products": [],
            "message": "Mock mode — products managed locally. Set SHOPIFY credentials to sync.",
            "mock": True,
        }

    import httpx

    url = f"https://{SHOPIFY_STORE_DOMAIN}/admin/api/2024-10/products.json?limit=250"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_ADMIN_TOKEN,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=headers)
            data = resp.json()

            if resp.status_code == 200:
                products = []
                for p in data.get("products", []):
                    for variant in p.get("variants", []):
                        products.append({
                            "shopify_product_id": str(p["id"]),
                            "shopify_variant_id": str(variant["id"]),
                            "name": p["title"],
                            "price": float(variant["price"]),
                            "slug": p.get("handle", ""),
                            "image_url": p.get("image", {}).get("src") if p.get("image") else None,
                        })
                return {"success": True, "products": products, "message": None, "mock": False}
            else:
                return {
                    "success": False,
                    "products": [],
                    "message": f"Shopify API error: {resp.status_code}",
                    "mock": False,
                }
    except Exception as e:
        return {"success": False, "products": [], "message": str(e), "mock": False}
