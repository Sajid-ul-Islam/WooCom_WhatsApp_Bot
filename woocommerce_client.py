import os
import logging
import httpx
from typing import List, Dict, Any, Optional

from utils import normalize_phone

logger = logging.getLogger(__name__)


class WooCommerceClient:
    def __init__(self):
        self.url = os.getenv("WOOCOMMERCE_URL", "").rstrip("/")
        self.key = os.getenv("WOOCOMMERCE_KEY")
        self.secret = os.getenv("WOOCOMMERCE_SECRET")

        if not self.url or not self.key or not self.secret:
            logger.warning("WooCommerce credentials not fully set in environment variables.")

        self.auth = (self.key, self.secret)
        self.base_api_url = f"{self.url}/wp-json/wc/v3"
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def get_categories(self, parent: int = 0, hide_empty: bool = True) -> List[Dict[str, Any]]:
        """Fetch product categories from WooCommerce."""
        url = f"{self.base_api_url}/products/categories"
        params = {
            "parent": parent,
            "hide_empty": str(hide_empty).lower(),
            "per_page": 50
        }
        try:
            response = await self._client.get(url, auth=self.auth, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching WooCommerce categories: {e}")
            return []

    async def get_products(self, category_id: Optional[int] = None, page: int = 1, per_page: int = 10) -> List[Dict[str, Any]]:
        """Fetch active products, optionally filtered by category."""
        url = f"{self.base_api_url}/products"
        params = {
            "status": "publish",
            "page": page,
            "per_page": per_page
        }
        if category_id:
            params["category"] = category_id

        try:
            response = await self._client.get(url, auth=self.auth, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching WooCommerce products: {e}")
            return []

    async def get_product(self, product_id: int) -> Optional[Dict[str, Any]]:
        """Fetch details of a single product."""
        url = f"{self.base_api_url}/products/{product_id}"
        try:
            response = await self._client.get(url, auth=self.auth)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching WooCommerce product {product_id}: {e}")
            return None

    async def search_products(self, query: str, page: int = 1, per_page: int = 10) -> List[Dict[str, Any]]:
        """Search products using WooCommerce search API."""
        url = f"{self.base_api_url}/products"
        params = {
            "status": "publish",
            "search": query,
            "page": page,
            "per_page": per_page
        }
        try:
            response = await self._client.get(url, auth=self.auth, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error searching WooCommerce products for query '{query}': {e}")
            return []

    async def get_all_products(self) -> List[Dict[str, Any]]:
        """Fetch all products (paginated) for syncing to Supabase database."""
        all_products = []
        page = 1
        per_page = 100
        while True:
            url = f"{self.base_api_url}/products"
            params = {
                "status": "publish",
                "page": page,
                "per_page": per_page
            }
            try:
                response = await self._client.get(url, auth=self.auth, params=params)
                response.raise_for_status()
                products = response.json()
                if not products:
                    break
                all_products.extend(products)
                logger.info(f"Fetched page {page} of products ({len(products)} products)")
                page += 1
            except Exception as e:
                logger.error(f"Error fetching product batch at page {page}: {e}")
                break
        return all_products

    async def create_order(self, phone_number: str, customer_name: str, cart_items: List[Dict[str, Any]], address_text: str = "") -> Optional[Dict[str, Any]]:
        """Create a new order in WooCommerce."""
        url = f"{self.base_api_url}/orders"

        # Parse cart items into WooCommerce format
        line_items = []
        for item in cart_items:
            line_items.append({
                "product_id": item["product_id"],
                "quantity": item["quantity"]
            })

        # Standard fallback for billing name splitting
        names = customer_name.split(" ", 1)
        first_name = names[0]
        last_name = names[1] if len(names) > 1 else ""

        payload = {
            "payment_method": "cod",
            "payment_method_title": "Cash on Delivery",
            "set_paid": False,
            "billing": {
                "first_name": first_name,
                "last_name": last_name,
                "address_1": address_text or "WhatsApp Checkout",
                "phone": phone_number,
                "email": f"{phone_number}@whatsapp.bot.temp"  # Dummy email required by WC if not provided
            },
            "shipping": {
                "first_name": first_name,
                "last_name": last_name,
                "address_1": address_text or "WhatsApp Checkout",
            },
            "line_items": line_items,
            "customer_note": "Ordered via WhatsApp Bot"
        }

        response = None
        try:
            response = await self._client.post(url, auth=self.auth, json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error creating WooCommerce order: {e}")
            if response is not None:
                logger.error(f"Response details: {response.text}")
            return None

    async def get_orders_by_phone(self, phone_number: str) -> List[Dict[str, Any]]:
        """Retrieve recent orders associated with a phone number."""
        url = f"{self.base_api_url}/orders"
        pn_clean = normalize_phone(phone_number)
        # Try searching by the raw phone number directly
        params = {
            "search": phone_number,
            "per_page": 10
        }
        try:
            response = await self._client.get(url, auth=self.auth, params=params)
            response.raise_for_status()
            orders = response.json()

            # Filter in memory: compare last 10 digits so country-code differences don't break matching
            matched = []
            for order in orders:
                billing_phone = order.get("billing", {}).get("phone", "")
                bp_clean = normalize_phone(billing_phone)
                # Match if the trailing digits overlap (at least 10)
                if pn_clean[-10:] == bp_clean[-10:]:
                    matched.append(order)
            return matched
        except Exception as e:
            logger.error(f"Error fetching orders for phone '{phone_number}': {e}")
            return []
