import os
import asyncio
import logging
from datetime import datetime, timezone
import json
from supabase import create_client, Client

from utils import normalize_phone

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

    async def add_to_cart(self, phone_number: str, product_id: int, name: str, price: float, quantity: int = 1, image_url: str = "", variation_id: int = None, variation_name: str = ""):
        if not self.client:
            return []
        phone = normalize_phone(phone_number)
        cart = await self.get_cart(phone)
        
        # Check if item exists (match product_id + variation_id so different sizes are separate items)
        found = False
        for item in cart:
            if item["product_id"] == product_id and item.get("variation_id") == variation_id:
                item["quantity"] += quantity
                found = True
                break
        
        if not found:
            item = {
                "product_id": product_id,
                "name": name,
                "price": float(price) if price else 0.0,
                "quantity": quantity,
                "image_url": image_url
            }
            if variation_id is not None:
                item["variation_id"] = variation_id
            if variation_name:
                item["variation_name"] = variation_name
            cart.append(item)
            
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

    async def get_abandoned_carts(self, hours: int = 24) -> list:
        """Fetch carts that have been inactive for exactly 'hours' to 'hours+1' to prevent spam."""
        if not self.client: return []
        try:
            res = await self._run_sync(
                lambda: self.client.table("carts").select("*").execute()
            )
            if not res.data: return []
            
            from datetime import datetime, timezone, timedelta
            now = datetime.now(timezone.utc)
            abandoned = []
            
            for c in res.data:
                try:
                    updated = datetime.fromisoformat(c["updated_at"].replace('Z', '+00:00'))
                    diff = now - updated
                    if timedelta(hours=hours) <= diff < timedelta(hours=hours+1):
                        items = c.get("items", [])
                        if items and len(items) > 0 and isinstance(items, list):
                            abandoned.append(c)
                except Exception:
                    pass
            return abandoned
        except Exception as e:
            logger.error(f"Error fetching abandoned carts: {e}")
            return []

    async def get_all_active_users(self) -> list:
        """Fetch all WhatsApp users."""
        if not self.client: return []
        try:
            res = await self._run_sync(
                lambda: self.client.table("whatsapp_users").select("phone_number").limit(1000).execute()
            )
            return [u["phone_number"] for u in (res.data or [])]
        except Exception as e:
            logger.error(f"Error fetching active users: {e}")
            return []

    # ==================== DASHBOARD STATS ====================

    async def get_dashboard_stats(self) -> dict:
        """Fetch aggregated stats for the dashboard."""
        if not self.client:
            return {"users": [], "orders": [], "carts_count": 0, "users_count": 0}
            
        stats = {
            "users": [],
            "orders": [],
            "carts_count": 0,
            "users_count": 0
        }
        
        try:
            # Get users
            users_res = await self._run_sync(
                lambda: self.client.table("whatsapp_users").select("phone_number, first_name, state, bot_paused, last_active").order("last_active", desc=True).limit(10).execute()
            )
            stats["users"] = users_res.data or []
            
            # Total users
            users_count_res = await self._run_sync(
                lambda: self.client.table("whatsapp_users").select("phone_number", count="exact").execute()
            )
            stats["users_count"] = users_count_res.count or 0
            
            # Get recent orders
            orders_res = await self._run_sync(
                lambda: self.client.table("orders").select("id, phone_number, status, total, created_at").order("created_at", desc=True).limit(5).execute()
            )
            stats["orders"] = orders_res.data or []
            
            # Active carts count
            carts_res = await self._run_sync(
                lambda: self.client.table("carts").select("items").execute()
            )
            if carts_res.data:
                stats["carts_count"] = sum(1 for c in carts_res.data if c.get("items"))
                
        except Exception as e:
            logger.error(f"Error fetching dashboard stats: {e}")
            
        return stats

    # ==================== SUPPORT TICKETS ====================

    async def create_support_ticket(self, phone_number: str, issue_type: str, order_id: int | None, description: str, priority: str = "normal") -> dict | None:
        """Create a new support ticket in Supabase."""
        if not self.client:
            return None
        phone = normalize_phone(phone_number)
        data = {
            "phone_number": phone,
            "issue_type": issue_type,
            "order_id": order_id,
            "description": description,
            "status": "open",
            "priority": priority,
        }
        try:
            response = await self._run_sync(
                lambda: self.client.table("support_tickets").insert(data).execute()
            )
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Error creating support ticket: {e}")
            return None

    # ==================== RATE LIMITING (Supabase-backed) ====================

    async def check_rate_limit(self, phone_number: str, max_requests: int = 5, window_seconds: int = 10) -> bool:
        """
        Check if a phone number has exceeded the rate limit.
        Uses Supabase for persistence across restarts/workers.
        Returns True if rate limited (should be blocked), False if allowed.
        """
        if not self.client:
            return False
        phone = normalize_phone(phone_number)
        try:
            from datetime import datetime, timezone, timedelta
            window_start = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
            return await self._check_rate_limit_fallback(phone, window_start, max_requests)
        except Exception as e:
            logger.warning(f"Rate limit check failed (falling through): {e}")
            return False

    async def _check_rate_limit_fallback(self, phone: str, window_start, max_requests: int) -> bool:
        """Fallback rate limit check using direct table queries."""
        try:
            from datetime import datetime, timezone
            # Count existing requests in the current window
            response = await self._run_sync(
                lambda: self.client.table("rate_limits")
                .select("id", count="exact")
                .eq("phone_number", phone)
                .gte("window_start", window_start.isoformat())
                .execute()
            )
            total = response.count if hasattr(response, 'count') and response.count else 0
            if total >= max_requests:
                return True

            # Record this request as a NEW row (insert, not upsert)
            # Using microsecond-precision timestamp ensures uniqueness
            now = datetime.now(timezone.utc)
            await self._run_sync(
                lambda: self.client.table("rate_limits").insert({
                    "phone_number": phone,
                    "window_start": now.isoformat(),
                    "request_count": 1
                }).execute()
            )
            return False
        except Exception as e:
            logger.warning(f"Rate limit fallback error: {e}")
            return False

    async def cleanup_rate_limits(self):
        """Remove expired rate limit entries (older than 1 hour)."""
        if not self.client:
            return
        try:
            from datetime import datetime, timezone, timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            await self._run_sync(
                lambda: self.client.table("rate_limits")
                .lt("window_start", cutoff)
                .delete()
                .execute()
            )
        except Exception as e:
            logger.warning(f"Rate limit cleanup error: {e}")

    # ==================== MESSAGE DEDUPLICATION (Supabase-backed) ====================

    async def is_duplicate_message(self, msg_id: str) -> bool:
        """Check if a message ID has already been processed."""
        if not self.client or not msg_id:
            return False
        try:
            response = await self._run_sync(
                lambda: self.client.table("processed_messages")
                .select("msg_id")
                .eq("msg_id", msg_id)
                .execute()
            )
            return len(response.data) > 0
        except Exception as e:
            logger.warning(f"Dedup check failed: {e}")
            return False

    async def mark_message_processed(self, msg_id: str):
        """Mark a message as processed to prevent future duplicates."""
        if not self.client or not msg_id:
            return
        try:
            from datetime import datetime, timezone
            await self._run_sync(
                lambda: self.client.table("processed_messages")
                .upsert({"msg_id": msg_id, "processed_at": datetime.now(timezone.utc).isoformat()})
                .execute()
            )
        except Exception as e:
            logger.warning(f"Failed to mark message processed: {e}")

    async def cleanup_processed_messages(self):
        """Remove processed message entries older than 1 hour (dedup window is 5 min)."""
        if not self.client:
            return
        try:
            from datetime import datetime, timezone, timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            await self._run_sync(
                lambda: self.client.table("processed_messages")
                .lt("processed_at", cutoff)
                .delete()
                .execute()
            )
        except Exception as e:
            logger.warning(f"Processed messages cleanup error: {e}")

    async def load_recent_processed_ids(self) -> set:
        """Load recently processed message IDs into memory on startup."""
        if not self.client:
            return set()
        try:
            from datetime import datetime, timezone, timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
            response = await self._run_sync(
                lambda: self.client.table("processed_messages")
                .select("msg_id")
                .gte("processed_at", cutoff)
                .execute()
            )
            return {row["msg_id"] for row in (response.data or [])}
        except Exception as e:
            logger.warning(f"Failed to load recent processed IDs: {e}")
            return set()

    # ==================== PENDING MESSAGES (Durable Queue) ====================

    async def create_pending_message(self, msg_id: str, phone_number: str, payload: dict) -> str | None:
        """Create a pending message record for durable processing."""
        if not self.client:
            return None
        phone = normalize_phone(phone_number)
        try:
            response = await self._run_sync(
                lambda: self.client.table("pending_messages")
                .insert({
                    "msg_id": msg_id,
                    "phone_number": phone,
                    "payload": payload,
                    "status": "pending"
                })
                .execute()
            )
            if response.data:
                return response.data[0].get("id")
            return None
        except Exception as e:
            logger.error(f"Error creating pending message: {e}")
            return None

    async def mark_pending_completed(self, pending_id: str, error: str = None):
        """Mark a pending message as completed or failed."""
        if not self.client or not pending_id:
            return
        try:
            from datetime import datetime, timezone
            update = {
                "status": "failed" if error else "completed",
                "processed_at": datetime.now(timezone.utc).isoformat()
            }
            if error:
                update["error"] = error[:500]
            await self._run_sync(
                lambda: self.client.table("pending_messages")
                .update(update)
                .eq("id", pending_id)
                .execute()
            )
        except Exception as e:
            logger.error(f"Error marking pending message: {e}")

    async def get_unprocessed_pending_messages(self) -> list:
        """Get pending messages that need processing (recovery on startup)."""
        if not self.client:
            return []
        try:
            from datetime import datetime, timezone, timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            response = await self._run_sync(
                lambda: self.client.table("pending_messages")
                .select("*")
                .in_("status", ["pending", "processing"])
                .gte("created_at", cutoff)
                .order("created_at", desc=False)
                .limit(50)
                .execute()
            )
            return response.data or []
        except Exception as e:
            logger.error(f"Error fetching pending messages: {e}")
            return []

    async def cleanup_old_pending_messages(self):
        """Remove completed/failed pending messages older than 24 hours."""
        if not self.client:
            return
        try:
            from datetime import datetime, timezone, timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            await self._run_sync(
                lambda: self.client.table("pending_messages")
                .in_("status", ["completed", "failed"])
                .lt("processed_at", cutoff)
                .delete()
                .execute()
            )
        except Exception as e:
            logger.warning(f"Pending messages cleanup error: {e}")

    async def claim_pending_message(self, pending_id: str) -> bool:
        """Atomically claim a pending message for processing (prevent double-processing)."""
        if not self.client:
            return False
        try:
            response = await self._run_sync(
                lambda: self.client.table("pending_messages")
                .update({"status": "processing"})
                .eq("id", pending_id)
                .eq("status", "pending")
                .execute()
            )
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error claiming pending message: {e}")
            return False

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