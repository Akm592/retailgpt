from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import httpx

logger = logging.getLogger("order_lookup")

# Maps internal category values → API query param values.
# Only categories listed here are supported by the orders API.
# If an internal category is not in this map, the API call is skipped.
CATEGORY_MAP: dict[str, str] = {
    "fb":          "F&B",
    "fashion":     "Fashion & Apparel",
    "electronics": "Electronics",
}


async def fetch_order_options(
    customer_id: str,
    category: str,
    base_url: str,
) -> Tuple[List[dict], Optional[str]]:
    """
    Calls GET {base_url}/api/customer/orders?customer_id=...&category=...

    Returns:
        (options, order_id)
        options  — list of {"id": str, "label": str} ready for suggestion buttons
        order_id — canonical order ID from the API response, or None

    Returns ([], None) on any error, unsupported category, or empty response.
    """
    if not base_url or not customer_id:
        logger.warning("Order lookup skipped: base_url or customer_id missing")
        return [], None

    api_category = CATEGORY_MAP.get(category.lower())
    if not api_category:
        logger.info(f"Order lookup skipped: category '{category}' not supported by orders API")
        return [], None
    url = f"{base_url.rstrip('/')}/api/customer/orders"
    params = {"customer_id": customer_id, "category": api_category}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        logger.error(f"Order lookup timed out for customer={customer_id} category={api_category}")
        return [], None
    except Exception as exc:
        logger.error(f"Order lookup failed: {exc}")
        return [], None

    if not data.get("success"):
        logger.warning(f"Order API returned success=false for customer={customer_id}")
        return [], None

    order     = data.get("order", {})
    order_id  = order.get("id") or data.get("order_id")
    past_orders: list = data.get("past_orders", [])

    if not past_orders:
        return [], order_id

    options: List[dict] = []
    for item in past_orders:
        product  = item.get("product", "Unknown item")
        qty      = item.get("quantity", 1)
        raw_date = item.get("ordered_at", "")
        try:
            dt       = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            date_str = dt.strftime("%b %d, %Y")
        except Exception:
            date_str = raw_date[:10] if raw_date else "—"

        label = f"{product}  ×{qty}  ({date_str})"
        # All items share the same order_id — the customer is picking the item,
        # but we record the parent order reference.
        options.append({"id": order_id or f"item_{len(options)}", "label": label})

    logger.info(
        f"Order lookup: customer={customer_id} category={api_category} "
        f"order_id={order_id} items={len(options)}"
    )
    return options, order_id
