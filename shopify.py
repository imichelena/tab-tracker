"""
Shopify integration layer.
Uses client_credentials OAuth flow on tab_tracker2 (Dev Dashboard app)
to get a fresh access token with write_draft_orders scope every 24h.

Token auto-refreshes when expired or missing.
"""
import time
import logging
import httpx
from config import (
    SHOPIFY_STORE_DOMAIN,
    SHOPIFY_ADMIN_TOKEN,  # fallback old token (read-only)
    SHOPIFY_LOCATION_ID,
    SHOPIFY_MOCK,
    SHOPIFY_CLIENT_ID,
    SHOPIFY_CLIENT_SECRET,
)

logger = logging.getLogger("tabtracker.shopify")

# Cached token
_cached_token: str | None = None
_token_expires: float = 0.0


async def get_access_token() -> str:
    """
    Get a valid Shopify access token via client_credentials grant.
    Caches the token and refreshes when within 5 minutes of expiry.
    """
    global _cached_token, _token_expires

    # Return cached token if still valid (5 min buffer)
    if _cached_token and time.time() < (_token_expires - 300):
        return _cached_token

    if SHOPIFY_MOCK or not SHOPIFY_CLIENT_ID:
        # Fallback to old static token (read-only, no draft orders)
        if SHOPIFY_ADMIN_TOKEN:
            return SHOPIFY_ADMIN_TOKEN
        raise RuntimeError("No Shopify credentials configured")

    # Exchange via client_credentials (form-encoded, NOT JSON)
    url = f"https://{SHOPIFY_STORE_DOMAIN}/admin/oauth/access_token"
    data = {
        "client_id": SHOPIFY_CLIENT_ID,
        "client_secret": SHOPIFY_CLIENT_SECRET,
        "grant_type": "client_credentials",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, data=data)  # form-encoded
        if resp.status_code == 200:
            result = resp.json()
            _cached_token = result["access_token"]
            _token_expires = time.time() + result.get("expires_in", 86399)
            logger.info(f"Shopify token refreshed, expires in {result.get('expires_in', 86399)}s")
            return _cached_token
        else:
            logger.error(f"Token exchange failed: {resp.status_code} {resp.text}")
            # Fallback to old token (read-only)
            if SHOPIFY_ADMIN_TOKEN:
                logger.warning("Falling back to static token (read-only, no draft orders)")
                return SHOPIFY_ADMIN_TOKEN
            raise RuntimeError(f"Shopify token exchange failed: {resp.text}")


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
    if SHOPIFY_MOCK:
        fake_id = f"gid://shopify/DraftOrder/{10_000_000 + tab_id}"
        logger.info(f"[MOCK] Draft order created for tab {tab_id}, total {total:.2f} EUR, {len(items)} line items")
        return {
            "success": True,
            "draft_order_id": fake_id,
            "admin_url": f"https://{SHOPIFY_STORE_DOMAIN or 'mock-store'}.myshopify.com/admin/draft_orders/{10_000_000 + tab_id}",
            "error": None,
            "mock": True,
        }

    # Get fresh token
    try:
        token = await get_access_token()
    except Exception as e:
        return {
            "success": False,
            "draft_order_id": None,
            "admin_url": None,
            "error": f"Token error: {e}",
            "mock": False,
        }

    # Build line items
    line_items = []
    for item in items:
        line_item = {
            "quantity": item["quantity"],
            "title": item["product_name"],
            "price": str(item["unit_price"]),
        }
        if item.get("shopify_variant_id"):
            line_item["variant_id"] = item["shopify_variant_id"]
        # Pass flavor info as line item properties (visible in Shopify order)
        if item.get("properties"):
            line_item["properties"] = item["properties"]
        line_items.append(line_item)

    payload = {
        "draft_order": {
            "line_items": line_items,
            "tags": "POS, in-store, tab-tracker",
            "note": f"Tab #{tab_id} - Created by Tab Tracker",
        }
    }

    url = f"https://{SHOPIFY_STORE_DOMAIN}/admin/api/2024-10/draft_orders.json"
    headers = {
        "X-Shopify-Access-Token": token,
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
    """
    if SHOPIFY_MOCK or not SHOPIFY_ADMIN_TOKEN:
        logger.info("[MOCK] Product sync requested — returning empty (use seed data)")
        return {
            "success": True,
            "products": [],
            "message": "Mock mode — products managed locally. Set SHOPIFY credentials to sync.",
            "mock": True,
        }

    try:
        token = await get_access_token()
    except Exception as e:
        return {"success": False, "products": [], "message": str(e), "mock": False}

    url = f"https://{SHOPIFY_STORE_DOMAIN}/admin/api/2024-10/products.json?limit=250"
    headers = {"X-Shopify-Access-Token": token}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=headers)
            data = resp.json()

            if resp.status_code == 200:
                products = []
                for p in data.get("products", []):
                    for variant in p.get("variants", []):
                        img_url = None
                        if p.get("images"):
                            img_url = p["images"][0].get("src")
                        products.append({
                            "shopify_product_id": str(p["id"]),
                            "shopify_variant_id": str(variant["id"]),
                            "name": p["title"],
                            "price": float(variant["price"]),
                            "slug": p.get("handle", ""),
                            "product_type": p.get("product_type", ""),
                            "image_url": img_url,
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
