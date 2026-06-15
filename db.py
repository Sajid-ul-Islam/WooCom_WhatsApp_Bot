import os
import re
import asyncio
import logging
from datetime import datetime, timezone
import json
from supabase import create_client, Client

logger = logging.getLogger(__name__)


def normalize_phone(phone: str) -> str:
    """Strip everything except digits from a phone number for consistent matching."""
    if not phone:
        return ""
    return re.sub(r"\D", "", phone)


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

    # ==================== HELPERS ====================

    def _run_sync(self, fn):
        """Run a synchronous Supabase call in a thread so we don't block the event loop."""
        return asyncio.to_thread(fn)

    # ==================== CART MANAGEMENT ====================

    async def get_cart(self, phone_number: str) -> list:
        if not self.client:
            return []
        phone = normalize_phone(phone_number)
        try:
            response = await self._run_sync(
                lambda: self.client.table("carts").select("items").eq("phone_number", phone).execute()
            )
            if response.data:
                return response.data[0].get("items", [])
            return []
        except Exception as e:
            logger.error(f"Error fetching cart for {phone}: {e}")
            return []

    async def add_to_cart(self, phone_number: str, product_id: int, name: str, price: float, quantity: int = 1, image_url: str = ""):
        if not self.client:
            return []
        phone = normalize_phone(phone_number)
        cart = await self.get_cart(phone)
        
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
            await self._run_sync(
                lambda: self.client.table("carts").upsert({
                    "phone_number": phone,
                    "items": cart,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }).execute()
            )
        except Exception as e:
            logger.error(f"Error updating cart for {phone}: {e}")
            
        return cart

    async def remove_from_cart(self, phone_number: str, product_id: int):
        if not self.client:
            return
        phone = normalize_phone(phone_number)
        cart = await self.get_cart(phone)
        updated_cart = [item for item in cart if item["product_id"] != product_id]
        
        try:
            await self._run_sync(
                lambda: self.client.table("carts").upsert({
                    "phone_number": phone,
                    "items": updated_cart,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }).execute()
            )
        except Exception as e:
            logger.error(f"Error removing from cart for {phone}: {e}")

    async def clear_cart(self, phone_number: str):
        if not self.client:
            return
        phone = normalize_phone(phone_number)
        try:
            await self._run_sync(
                lambda: self.client.table("carts").upsert({
                    "phone_number": phone,
                    "items": [],
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }).execute()
            )
        except Exception as e:
            logger.error(f"Error clearing cart for {phone}: {e}")

    # ==================== ORDER CACHE ====================

    async def cache_orders(self, orders: list, phone_number: str):
        if not self.client or not orders:
            return
        phone = normalize_phone(phone_number)
        try:
            rows = []
            for o in orders:
                # Store enough to show history without calling WC
                rows.append({
                    "id": o["id"],
                    "phone_number": phone,
                    "status": o.get("status", "pending"),
                    "total": float(o.get("total", 0)),
                    "items": o.get("line_items", []),
                    "created_at": o.get("date_created", datetime.now(timezone.utc).isoformat())
                })
            await self._run_sync(
                lambda: self.client.table("orders").upsert(rows).execute()
            )
        except Exception as e:
            logger.error(f"Error caching orders: {e}")

    async def get_cached_orders(self, phone_number: str) -> list:
        if not self.client:
            return []
        phone = normalize_phone(phone_number)
        try:
            response = await self._run_sync(
                lambda: self.client.table("orders").select("*").eq("phone_number", phone).order("created_at", desc=True).execute()
            )
            return response.data or []
        except Exception as e:
            logger.error(f"Error fetching cached orders: {e}")
            return []

    # ==================== VECTOR SEARCH ====================

    async def match_products(self, query_embedding: list, threshold: float = 0.4, limit: int = 4):
        if not self.client:
            return []
        try:
            response = await self._run_sync(
                lambda: self.client.rpc(
                    "match_products",
                    {"query_embedding": query_embedding, "match_threshold": threshold, "match_count": limit}
                ).execute()
            )
            return response.data or []
        except Exception as e:
            logger.error(f"Error matching products vector: {e}")
            return []

    # ==================== USER MANAGEMENT & HISTORY ====================

    async def upsert_user(self, phone_number: str, first_name: str = None):
        """Create or update WhatsApp user"""
        if not self.client:
            return
        phone = normalize_phone(phone_number)
        try:
            data = {
                "phone_number": phone,
                "first_name": first_name or "Customer",
                "last_active": datetime.now(timezone.utc).isoformat()
            }
            await self._run_sync(
                lambda: self.client.table("whatsapp_users").upsert(data).execute()
            )
        except Exception as e:
            logger.error(f"Error upserting user {phone}: {e}")

    async def get_user_history(self, phone_number: str) -> list:
        """Get conversation history"""
        if not self.client:
            return []
        phone = normalize_phone(phone_number)
        try:
            response = await self._run_sync(
                lambda: self.client.table("whatsapp_users").select("chat_history").eq("phone_number", phone).execute()
            )
            if response.data and len(response.data) > 0:
                history = response.data[0].get("chat_history", [])
                return history if isinstance(history, list) else []
        except Exception as e:
            logger.error(f"Error getting history for {phone}: {e}")
        return []

    async def update_user_history(self, phone_number: str, history: list):
        """Save updated conversation history"""
        if not self.client:
            return
        phone = normalize_phone(phone_number)
        try:
            await self._run_sync(
                lambda: self.client.table("whatsapp_users").update({"chat_history": history}).eq("phone_number", phone).execute()
            )
        except Exception as e:
            logger.error(f"Error updating history for {phone}: {e}")

    async def set_bot_paused(self, phone_number: str, is_paused: bool):
        """Pause or resume the bot for human handoff"""
        if not self.client:
            return
        phone = normalize_phone(phone_number)
        try:
            # Ensure user exists first
            await self.upsert_user(phone)
            await self._run_sync(
                lambda: self.client.table("whatsapp_users").update({"bot_paused": is_paused}).eq("phone_number", phone).execute()
            )
        except Exception as e:
            logger.error(f"Error setting bot_paused for {phone}: {e}")
            
    async def is_bot_paused(self, phone_number: str) -> bool:
        """Check if bot is paused"""
        if not self.client:
            return False
        phone = normalize_phone(phone_number)
        try:
            response = await self._run_sync(
                lambda: self.client.table("whatsapp_users").select("bot_paused").eq("phone_number", phone).execute()
            )
            if response.data and len(response.data) > 0:
                return response.data[0].get("bot_paused", False)
        except Exception as e:
            logger.error(f"Error checking bot_paused for {phone}: {e}")
        return False

    # ==================== USER STATE MACHINE ====================

    async def get_user_state(self, phone_number: str) -> str:
        """Get the current conversational state for a user (e.g. 'idle', 'checkout_pending')."""
        if not self.client:
            return "idle"
        phone = normalize_phone(phone_number)
        try:
            response = await self._run_sync(
                lambda: self.client.table("whatsapp_users").select("state").eq("phone_number", phone).execute()
            )
            if response.data and len(response.data) > 0:
                return response.data[0].get("state") or "idle"
        except Exception as e:
            logger.error(f"Error getting user state for {phone}: {e}")
        return "idle"

    async def set_user_state(self, phone_number: str, state: str):
        """Set the conversational state for a user."""
        if not self.client:
            return
        phone = normalize_phone(phone_number)
        try:
            await self._run_sync(
                lambda: self.client.table("whatsapp_users").update({"state": state}).eq("phone_number", phone).execute()
            )
        except Exception as e:
            logger.error(f"Error setting user state for {phone}: {e}")

    # ==================== APP CONFIG / SECRETS ====================

    async def get_app_config(self) -> dict:
        """
        Fetch all key-value pairs from the 'config' table in Supabase.
        Expected table schema:  key (TEXT PK), value (TEXT)
        Returns a dict like: {"OPENAI_API_KEY": "sk-...", "LLM_PROVIDER": "openai", ...}
        """
        if not self.client:
            return {}
        try:
            response = await self._run_sync(
                lambda: self.client.table("config").select("key, value").execute()
            )
            if response.data:
                return {row["key"]: row["value"] for row in response.data}
            return {}
        except Exception as e:
            logger.error(f"Error fetching app config from Supabase: {e}")
            return {}

    # ==================== PRODUCT SYNC ====================

    async def upsert_product(self, doc: dict) -> bool:
        """Upsert a single product document (with embedding) into the 'products' table."""
        if not self.client:
            return False
        try:
            await self._run_sync(
                lambda: self.client.table("products").upsert(doc).execute()
            )
            return True
        except Exception as e:
            logger.error(f"Error upserting product {doc.get('id')}: {e}")
            return False