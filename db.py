import os
import logging
from typing import List, Dict, Any, Optional
from supabase import create_client, Client

logger = logging.getLogger(__name__)

class DatabaseClient:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        
        if not self.url or not self.key:
            logger.warning("Supabase URL or Key not set in environment variables.")
            self.client = None
        else:
            try:
                self.client: Client = create_client(self.url, self.key)
            except Exception as e:
                logger.error(f"Failed to initialize Supabase client: {e}")
                self.client = None

    # --- Cart Operations ---
    async def get_cart(self, phone_number: str) -> List[Dict[str, Any]]:
        """Retrieve items in user's shopping cart."""
        if not self.client:
            return []
        try:
            # Query carts table
            response = self.client.table("carts").select("items").eq("phone_number", phone_number).execute()
            if response.data and len(response.data) > 0:
                return response.data[0].get("items", [])
            return []
        except Exception as e:
            logger.error(f"Error getting cart for {phone_number}: {e}")
            return []

    async def add_to_cart(self, phone_number: str, product_id: int, name: str, price: float, quantity: int = 1, image_url: str = "") -> List[Dict[str, Any]]:
        """Add product to cart or increment quantity if already exists."""
        if not self.client:
            return []
        try:
            cart_items = await self.get_cart(phone_number)
            
            # Check if item already exists in cart
            item_exists = False
            for item in cart_items:
                if item["product_id"] == product_id:
                    item["quantity"] += quantity
                    item_exists = True
                    break
                    
            if not item_exists:
                cart_items.append({
                    "product_id": product_id,
                    "name": name,
                    "price": float(price) if price else 0.0,
                    "quantity": quantity,
                    "image_url": image_url
                })
                
            # Save cart back to database
            self.client.table("carts").upsert({
                "phone_number": phone_number,
                "items": cart_items
            }).execute()
            
            return cart_items
        except Exception as e:
            logger.error(f"Error adding to cart for {phone_number}: {e}")
            return []

    async def remove_from_cart(self, phone_number: str, product_id: int) -> List[Dict[str, Any]]:
        """Remove product from cart."""
        if not self.client:
            return []
        try:
            cart_items = await self.get_cart(phone_number)
            cart_items = [item for item in cart_items if item["product_id"] != product_id]
            
            self.client.table("carts").upsert({
                "phone_number": phone_number,
                "items": cart_items
            }).execute()
            
            return cart_items
        except Exception as e:
            logger.error(f"Error removing from cart for {phone_number}: {e}")
            return []

    async def update_cart_quantity(self, phone_number: str, product_id: int, quantity: int) -> List[Dict[str, Any]]:
        """Update the quantity of a specific item in the cart. If quantity <= 0, remove item."""
        if quantity <= 0:
            return await self.remove_from_cart(phone_number, product_id)
            
        if not self.client:
            return []
        try:
            cart_items = await self.get_cart(phone_number)
            for item in cart_items:
                if item["product_id"] == product_id:
                    item["quantity"] = quantity
                    break
                    
            self.client.table("carts").upsert({
                "phone_number": phone_number,
                "items": cart_items
            }).execute()
            
            return cart_items
        except Exception as e:
            logger.error(f"Error updating cart quantity for {phone_number}: {e}")
            return []

    async def clear_cart(self, phone_number: str) -> bool:
        """Clear all items in user's cart."""
        if not self.client:
            return False
        try:
            self.client.table("carts").upsert({
                "phone_number": phone_number,
                "items": []
            }).execute()
            return True
        except Exception as e:
            logger.error(f"Error clearing cart for {phone_number}: {e}")
            return False

    # --- Product Caching and Vector Search ---
    async def upsert_product(self, product_data: Dict[str, Any]) -> bool:
        """Upsert a product into the products table (including embedding)."""
        if not self.client:
            return False
        try:
            self.client.table("products").upsert(product_data).execute()
            return True
        except Exception as e:
            logger.error(f"Error upserting product {product_data.get('id')}: {e}")
            return False

    async def match_products(self, query_embedding: List[float], threshold: float = 0.5, limit: int = 5) -> List[Dict[str, Any]]:
        """Search products using vector similarity (calls RPC function)."""
        if not self.client:
            return []
        try:
            response = self.client.rpc("match_products", {
                "query_embedding": query_embedding,
                "match_threshold": threshold,
                "match_count": limit
            }).execute()
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Error executing vector similarity search: {e}")
            return []

    # --- Order History Cache ---
    async def cache_orders(self, orders_list: List[Dict[str, Any]], phone_number: str) -> None:
        """Cache user orders for quick status checking."""
        if not self.client:
            return
        try:
            for order in orders_list:
                order_id = order.get("id")
                # Parse items out of order
                line_items = []
                for item in order.get("line_items", []):
                    line_items.append({
                        "name": item.get("name"),
                        "quantity": item.get("quantity"),
                        "price": item.get("price")
                    })
                
                self.client.table("orders").upsert({
                    "id": order_id,
                    "phone_number": phone_number,
                    "status": order.get("status"),
                    "total": float(order.get("total", 0.0)),
                    "items": line_items,
                    "created_at": order.get("date_created")
                }).execute()
        except Exception as e:
            logger.error(f"Error caching orders: {e}")

    async def get_cached_orders(self, phone_number: str) -> List[Dict[str, Any]]:
        """Retrieve user's order history from the database cache."""
        if not self.client:
            return []
        try:
            response = self.client.table("orders").select("*").eq("phone_number", phone_number).order("created_at", desc=True).execute()
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Error retrieving cached orders: {e}")
            return []
