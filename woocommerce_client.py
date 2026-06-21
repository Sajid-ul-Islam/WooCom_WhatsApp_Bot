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

    async def _request(self, method: str, url: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Make an HTTP request with consistent error handling."""
        try:
            response = await self._client.request(method, url, auth=self.auth, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"WooCommerce HTTP {e.response.status_code} for {method} {url}: {e.response.text[:500]}")
            return None
        except httpx.ConnectError as e:
            logger.error(f"WooCommerce connection error for {url}: {e}")
            return None
        except httpx.TimeoutException as e:
            logger.error(f"WooCommerce timeout for {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected WooCommerce error for {url}: {e}")
            return None

    async def _request_list(self, method: str, url: str, **kwargs) -> list:
        """Make an HTTP request expecting a list response."""
        try:
            response = await self._client.request(method, url, auth=self.auth, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"WooCommerce HTTP {e.response.status_code} for {method} {url}: {e.response.text[:300]}")
            return []
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.error(f"WooCommerce connection timeout for {url}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected WooCommerce error for {url}: {e}")
            return []

    async def get_categories(self, parent: int = 0, hide_empty: bool = True) -> List[Dict[str, Any]]:
        """Fetch product categories from WooCommerce."""
        url = f"{self.base_api_url}/products/categories"
        params = {
            "parent": parent,
            "hide_empty": str(hide_empty).lower(),
            "per_page": 50
        }
        result = await self._request_list("GET", url, params=params)
        if isinstance(result, list):
            return result
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

        result = await self._request_list("GET", url, params=params)
        if isinstance(result, list):
            return result
        return []

    async def get_product(self, product_id: int) -> Optional[Dict[str, Any]]:
        """Fetch details of a single product."""
        url = f"{self.base_api_url}/products/{product_id}"
        return await self._request("GET", url)

    async def search_products(self, query: str, page: int = 1, per_page: int = 10) -> List[Dict[str, Any]]:
        """Search products using WooCommerce search API."""
        url = f"{self.base_api_url}/products"
        params = {
            "status": "publish",
            "search": query,
            "page": page,
            "per_page": per_page
        }
        result = await self._request_list("GET", url, params=params)
        if isinstance(result, list):
            return result
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
            products = await self._request_list("GET", url, params=params)
            if not products:
                break
            all_products.extend(products)
            logger.info(f"Fetched page {page} of products ({len(products)} products)")
            page += 1
        return all_products

    async def create_order(self, phone_number: str, customer_name: str, cart_items: List[Dict[str, Any]], address_text: str = "") -> Optional[Dict[str, Any]]:
        """Create a new order in WooCommerce."""
        url = f"{self.base_api_url}/orders"

        # Parse cart items into WooCommerce format
        line_items = []
        for item in cart_items:
            line_item = {
                "product_id": item["product_id"],
                "quantity": item["quantity"]
            }
            # Pass variation_id if the item is a product variation (e.g. a specific size)
            if item.get("variation_id"):
                line_item["variation_id"] = item["variation_id"]
            line_items.append(line_item)

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

        return await self._request("POST", url, json=payload)

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
        except httpx.HTTPStatusError as e:
            logger.error(f"WooCommerce HTTP {e.response.status_code} fetching orders for {phone_number}: {e.response.text[:300]}")
            return []
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.error(f"WooCommerce connection error fetching orders for {phone_number}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching orders for phone '{phone_number}': {e}")
            return []

    async def update_order_status(self, order_id: int, status: str) -> Optional[Dict[str, Any]]:
        """Update an order status in WooCommerce (e.g. to cancel it)."""
        url = f"{self.base_api_url}/orders/{order_id}"
        payload = {"status": status}
        return await self._request("PUT", url, json=payload)

    async def create_order_note(self, order_id: int, note: str) -> Optional[Dict[str, Any]]:
        """Create a note on a WooCommerce order."""
        url = f"{self.base_api_url}/orders/{order_id}/notes"
        payload = {"note": note}
        return await self._request("POST", url, json=payload)

    async def get_product_variations(self, product_id: int) -> List[Dict[str, Any]]:
        """Fetch all variations for a variable product (e.g. different sizes)."""
        url = f"{self.base_api_url}/products/{product_id}/variations"
        all_variations = []
        page = 1
        per_page = 100
        while True:
            params = {"page": page, "per_page": per_page}
            variations = await self._request_list("GET", url, params=params)
            if not variations:
                break
            all_variations.extend(variations)
            page += 1
        return all_variations

    async def get_product_variation(self, product_id: int, variation_id: int) -> Optional[Dict[str, Any]]:
        """Fetch details of a single variation (e.g. a specific size)."""
        url = f"{self.base_api_url}/products/{product_id}/variations/{variation_id}"
        return await self._request("GET", url)

    async def get_order(self, order_id: int) -> Optional[Dict[str, Any]]:
        """Fetch details of a single order."""
        url = f"{self.base_api_url}/orders/{order_id}"
        return await self._request("GET", url)

