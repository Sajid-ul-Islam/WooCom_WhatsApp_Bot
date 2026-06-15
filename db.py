import os
import logging
from datetime import datetime, timezone
import json
from supabase import create_client, Client

logger = logging.getLogger(__name__)

class DatabaseClient:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        self.client: Client | None = None
        
        if self.url and self.key:
            try:
                self.client = create_client(self.url, self.key)
                logger.info("✅ Supabase connected successfully for WhatsApp bot")
            except Exception as e:
                logger.error(f"Failed to connect to Supabase: {e}")
        else:
            logger.warning("Supabase credentials not found in environment")

    # ==================== CART MANAGEMENT ====================

    async def get_cart(self, phone_number: str) -> list:
        if not self.client:
            return []
        try:
            response = self.client.table("carts").select("items").eq("phone_number", phone_number).execute()
            if response.data:
                return response.data[0].get("items", [])
            return []
        except Exception as e:
            logger.error(f"Error fetching cart for {phone_number}: {e}")
            return []

    async def add_to_cart(self, phone_number: str, product_id: int, name: str, price: float, quantity: int = 1, image_url: str = ""):
        if not self.client:
            return []
        cart = await self.get_cart(phone_number)
        
        # Check if item exists
        found = False
        for item in cart:
            if item["product_id"] == product_id:
                item["quantity"] += quantity
                found = True
                break
        
        if not found:
            cart.append({
                "product_id": product_id,
                "name": name,
                "price": float(price) if price else 0.0,
                "quantity": quantity,
                "image_url": image_url
            })
            
        try:
            self.client.table("carts").upsert({
                "phone_number": phone_number,
                "items": cart,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }).execute()
        except Exception as e:
            logger.error(f"Error updating cart for {phone_number}: {e}")
            
        return cart

    async def remove_from_cart(self, phone_number: str, product_id: int):
        if not self.client:
            return
        cart = await self.get_cart(phone_number)
        updated_cart = [item for item in cart if item["product_id"] != product_id]
        
        try:
            self.client.table("carts").upsert({
                "phone_number": phone_number,
                "items": updated_cart,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }).execute()
        except Exception as e:
            logger.error(f"Error removing from cart for {phone_number}: {e}")

    async def clear_cart(self, phone_number: str):
        if not self.client:
            return
        try:
            self.client.table("carts").upsert({
                "phone_number": phone_number,
                "items": [],
                "updated_at": datetime.now(timezone.utc).isoformat()
            }).execute()
        except Exception as e:
            logger.error(f"Error clearing cart for {phone_number}: {e}")

    # ==================== ORDER CACHE ====================

    async def cache_orders(self, orders: list, phone_number: str):
        if not self.client or not orders:
            return
        try:
            rows = []
            for o in orders:
                # Store enough to show history without calling WC
                rows.append({
                    "id": o["id"],
                    "phone_number": phone_number,
                    "status": o.get("status", "pending"),
                    "total": float(o.get("total", 0)),
                    "items": o.get("line_items", []),
                    "created_at": o.get("date_created", datetime.now(timezone.utc).isoformat())
                })
            self.client.table("orders").upsert(rows).execute()
        except Exception as e:
            logger.error(f"Error caching orders: {e}")

    async def get_cached_orders(self, phone_number: str) -> list:
        if not self.client:
            return []
        try:
            response = self.client.table("orders").select("*").eq("phone_number", phone_number).order("created_at", desc=True).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error fetching cached orders: {e}")
            return []

    # ==================== VECTOR SEARCH ====================

    async def match_products(self, query_embedding: list, threshold: float = 0.4, limit: int = 4):
        if not self.client:
            return []
        try:
            response = self.client.rpc(
                "match_products",
                {"query_embedding": query_embedding, "match_threshold": threshold, "match_count": limit}
            ).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error matching products vector: {e}")
            return []

    # ==================== USER MANAGEMENT & HISTORY ====================

    async def upsert_user(self, phone_number: str, first_name: str = None):
        """Create or update WhatsApp user"""
        if not self.client:
            return
        try:
            data = {
                "phone_number": phone_number,
                "first_name": first_name or "Customer",
                "last_active": datetime.now(timezone.utc).isoformat()
            }
            self.client.table("whatsapp_users").upsert(data).execute()
        except Exception as e:
            logger.error(f"Error upserting user {phone_number}: {e}")

    async def get_user_history(self, phone_number: str) -> list:
        """Get conversation history"""
        if not self.client:
            return []
        try:
            response = self.client.table("whatsapp_users").select("chat_history").eq("phone_number", phone_number).execute()
            if response.data and len(response.data) > 0:
                history = response.data[0].get("chat_history", [])
                return history if isinstance(history, list) else []
        except Exception as e:
            logger.error(f"Error getting history for {phone_number}: {e}")
        return []

    async def update_user_history(self, phone_number: str, history: list):
        """Save updated conversation history"""
        if not self.client:
            return
        try:
            self.client.table("whatsapp_users").update({"chat_history": history}).eq("phone_number", phone_number).execute()
        except Exception as e:
            logger.error(f"Error updating history for {phone_number}: {e}")

    async def set_bot_paused(self, phone_number: str, is_paused: bool):
        """Pause or resume the bot for human handoff"""
        if not self.client:
            return
        try:
            # Ensure user exists first
            await self.upsert_user(phone_number)
            self.client.table("whatsapp_users").update({"bot_paused": is_paused}).eq("phone_number", phone_number).execute()
        except Exception as e:
            logger.error(f"Error setting bot_paused for {phone_number}: {e}")
            
    async def is_bot_paused(self, phone_number: str) -> bool:
        """Check if bot is paused"""
        if not self.client:
            return False
        try:
            response = self.client.table("whatsapp_users").select("bot_paused").eq("phone_number", phone_number).execute()
            if response.data and len(response.data) > 0:
                return response.data[0].get("bot_paused", False)
        except Exception as e:
            logger.error(f"Error checking bot_paused for {phone_number}: {e}")
        return False