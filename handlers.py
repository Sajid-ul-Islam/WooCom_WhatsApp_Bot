import re
import asyncio
import logging

from context import BotContext
from i18n import get_text

# Import modularized handlers
from shopping_handlers import (
    handle_main_menu,
    handle_categories,
    handle_category_products,
    handle_product_detail,
    handle_show_variations,
    handle_size_chart,
    handle_ai_search,
    handle_sku_search,
    handle_recommend_for_you,
)
from cart_handlers import (
    handle_add_to_cart,
    handle_add_variation_to_cart,
    handle_remove_from_cart,
    handle_view_cart,
    handle_checkout_prompt,
    handle_process_checkout,
    handle_place_order,
    handle_clear_cart,
)
from support_handlers import (
    handle_human_agent,
    _handle_wit_resume_bot,
)
from account_handlers import (
    handle_view_orders,
    handle_size_rec_start,
    handle_size_rec_height,
    handle_size_rec_weight,
    handle_cancel_order_request,
    handle_cancel_order_confirm,
    handle_cancel_order_keep,
    handle_change_language,
)

logger = logging.getLogger(__name__)


# ==================== DISPATCH TABLES ====================

ACTION_HANDLERS = {
    "menu_main": handle_main_menu,
    "menu_categories": handle_categories,
    "menu_cart": handle_view_cart,
    "menu_orders": handle_view_orders,
    "menu_human": handle_human_agent,
    "cart_checkout": handle_checkout_prompt,
    "cart_clear": handle_clear_cart,
    "menu_size": handle_size_rec_start,
    "menu_recommend": handle_recommend_for_you,
    "menu_cancel_order": lambda ctx, to: handle_cancel_order_request(ctx, to, ""),
    "menu_language": handle_change_language,
}

PREFIX_HANDLERS = [
    ("cat_", handle_category_products),
    ("prod_", handle_product_detail),
    ("add_", handle_add_to_cart),
    ("size_sel_", handle_show_variations),
    ("size_chart_", handle_size_chart),
    ("rmv_", handle_remove_from_cart),
    ("order_cancel_confirm_", lambda ctx, to, order_id: handle_cancel_order_confirm(ctx, to, order_id)),
]


# Map Wit.ai intent names → async handlers (used inside route_text)
WIT_INTENT_MAP = {
    "greeting": handle_main_menu,
    "browse_categories": handle_categories,
    "view_cart": handle_view_cart,
    "view_orders": handle_view_orders,
    "size_help": handle_size_rec_start,
    "cancel_order": lambda ctx, to: handle_cancel_order_request(ctx, to, ""),
    "talk_to_human": handle_human_agent,
    "resume_bot": _handle_wit_resume_bot,
    "clear_cart": handle_clear_cart,
    "checkout": handle_checkout_prompt,
}


TEXT_COMMANDS = {
    "/start": handle_main_menu,
    "hi": handle_main_menu,
    "hello": handle_main_menu,
    "menu": handle_main_menu,
    "hey": handle_main_menu,
    "assalamu alaikum": handle_main_menu,
    "start": handle_main_menu,
    "categories": handle_categories,
    "browse": handle_categories,
    "catalog": handle_categories,
    "cart": handle_view_cart,
    "shopping cart": handle_view_cart,
    "view cart": handle_view_cart,
    "orders": handle_view_orders,
    "my order": handle_view_orders,
    "my orders": handle_view_orders,
    "status": handle_view_orders,
    "/talktohuman": handle_human_agent,
    "talk to human": handle_human_agent,
    "human": handle_human_agent,
    "support": handle_human_agent,
    "size": handle_size_rec_start,
    "size guide": handle_size_rec_start,
    "size chart": handle_size_rec_start,
    "size recommendation": handle_size_rec_start,
    "whats my size": handle_size_rec_start,
    "cancel order": lambda ctx, to: handle_cancel_order_request(ctx, to, ""),
    "order cancellation": lambda ctx, to: handle_cancel_order_request(ctx, to, ""),
}


# ==================== ROUTING ====================


async def route_action(ctx: BotContext, to: str, action_id: str) -> bool:
    """Route an interactive action to the appropriate handler. Returns True if handled."""
    # Handle COD checkout confirmation click
    if action_id == "checkout_place":
        user_state = await ctx.db.get_user_state(to)
        if user_state.startswith("checkout_confirm|"):
            parts = user_state.split("|", 2)
            if len(parts) == 3:
                await handle_place_order(ctx, to, parts[1], parts[2])
                return True
        await ctx.db.set_user_state(to, "idle")
        lang = await ctx.db.get_user_language(to)
        await ctx.wa.send_text_message(to, get_text(lang, "session_expired"))
        await handle_main_menu(ctx, to)
        return True

    if action_id == "checkout_cancel":
        lang = await ctx.db.get_user_language(to)
        await ctx.db.set_user_state(to, "idle")
        await ctx.wa.send_text_message(to, get_text(lang, "checkout_cancelled"))
        await handle_main_menu(ctx, to)
        return True

    # Handle order cancellation abort click
    if action_id == "order_cancel_keep":
        await handle_cancel_order_keep(ctx, to)
        return True

    # Exact match
    if action_id in ACTION_HANDLERS:
        await ACTION_HANDLERS[action_id](ctx, to)
        return True

    # Handle "varadd_{product_id}_{variation_id}" prefix specially (needs two ints)
    if action_id.startswith("varadd_"):
        parts = action_id[7:].split("_")
        if len(parts) == 2:
            try:
                await handle_add_variation_to_cart(ctx, to, int(parts[0]), int(parts[1]))
                return True
            except ValueError:
                pass

    # Prefix match (e.g. "cat_123" -> handle_category_products(ctx, to, 123))
    for prefix, handler in PREFIX_HANDLERS:
        if action_id.startswith(prefix):
            id_str = action_id[len(prefix):]
            await handler(ctx, to, int(id_str))
            return True

    return False


async def route_text(ctx: BotContext, to: str, text: str):
    """Route a text message to the appropriate handler.

    Priority order:
    1. Exact keyword match (fastest — no external call)
    2. Regex pattern match (cancel order, add X, remove X, checkout:)
    3. Wit.ai intent classification (fast — ~50 ms, free)
    4. LLM fallback (expensive — only for complex/unrecognised queries)
    """
    text_lower = text.lower().strip()

    # === 1. Exact keyword match ===
    if text_lower in TEXT_COMMANDS:
        await TEXT_COMMANDS[text_lower](ctx, to)
        return

    # === 1.5. SKU code detection ===
    # SKUs are short alphanumeric codes (3-20 chars) with at least one letter AND one digit.
    # This runs before Wit.ai and LLM to give a fast, direct product-lookup response.
    sku_match = re.match(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,19}$", text.strip())
    if sku_match and re.search(r"[A-Za-z]", text) and re.search(r"[0-9]", text):
        logger.info(f"Input '{text}' looks like an SKU — attempting SKU lookup.")
        await handle_sku_search(ctx, to, text.strip())
        return

    # === 2. Regex pattern match ===
    cancel_match = re.match(r"^cancel\s+order\s+(\d+)", text_lower)
    if cancel_match:
        await handle_cancel_order_request(ctx, to, cancel_match.group(1))
        return

    add_match = re.match(r"^add\s+(\d+)", text_lower)
    if add_match:
        try:
            await handle_add_to_cart(ctx, to, int(add_match.group(1)))
        except (ValueError, KeyError) as e:
            logger.warning(f"Add to cart error for {to}: {e}")
            await ctx.wa.send_text_message(
                to, "To add a product, please type *Add [Product ID]* (e.g. *Add 105*)."
            )
        return

    remove_match = re.match(r"^remove\s+(\d+)", text_lower)
    if remove_match:
        try:
            await handle_remove_from_cart(ctx, to, int(remove_match.group(1)))
        except (ValueError, KeyError) as e:
            logger.warning(f"Remove from cart error for {to}: {e}")
            await ctx.wa.send_text_message(
                to, "To remove an item, type *Remove [Product ID]* (e.g. *Remove 105*)."
            )
        return

    if text_lower.startswith("checkout:"):
        details_text = text.split(":", 1)[1].strip()
        await handle_process_checkout(ctx, to, details_text)
        return

    # === 3. Wit.ai intent classification (fast path) ===
    if ctx.wit and ctx.wit.configured:
        wit_result = await ctx.wit.analyze_message(text)
        if wit_result and wit_result["intents"]:
            top_intent = wit_result["intents"][0]
            intent_name = top_intent["name"]
            confidence = top_intent["confidence"]
            logger.info(f"Wit.ai classified '{text}' as '{intent_name}' (confidence={confidence:.2f})")

            # Use Wit.ai result if confidence >= 0.6
            if confidence >= 0.6 and intent_name in WIT_INTENT_MAP:
                handler = WIT_INTENT_MAP[intent_name]
                await handler(ctx, to)
                return

            # For product_search intent or low-confidence intents, extract search entities
            if intent_name == "product_search" or confidence < 0.6:
                # Extract product name entities if present
                entities = wit_result.get("entities", {})
                product_entity = entities.get("product", [])
                if product_entity:
                    # Use the highest-confidence product entity as the search term
                    best = max(product_entity, key=lambda e: e.get("confidence", 0))
                    search_text = best.get("value", text)
                else:
                    search_text = text

                # Route product_search to AI search
                if intent_name == "product_search":
                    await handle_ai_search(ctx, to, search_text)
                    return

    # === 4. LLM fallback (expensive — complex/unrecognised queries) ===
    await handle_ai_search(ctx, to, text)


# ==================== MESSAGE PROCESSING ====================


async def process_incoming_message(
    ctx: BotContext, from_number: str, message: dict,
    value: dict, action_id: str, incoming_text: str,
    pending_id: str | None = None
):
    """Processes WhatsApp message in the background to avoid blocking response to Meta.
    
    If pending_id is provided, it will be marked as completed/failed after processing.
    """
    try:
        # Upsert user on every message
        contact_name = None
        contacts = value.get("contacts", [])
        if contacts:
            profile = contacts[0].get("profile", {})
            contact_name = profile.get("name")
        await ctx.db.upsert_user(from_number, first_name=contact_name)

        # --- Resume bot check (always runs even if paused) ---
        if incoming_text:
            text_lower = incoming_text.lower()
            if text_lower in ["/resume", "resume", "resume bot"]:
                await ctx.db.set_bot_paused(from_number, False)
                await ctx.db.set_user_state(from_number, "idle")
                lang = await ctx.db.get_user_language(from_number)
                await ctx.wa.send_text_message(from_number, get_text(lang, "bot_resumed"))
                return

        is_paused = await ctx.db.is_bot_paused(from_number)
        if is_paused:
            logger.info(f"Bot paused for {from_number}. Ignoring message.")
            return

        # --- State machine checking ---
        user_state = await ctx.db.get_user_state(from_number)

        if incoming_text and incoming_text.lower() in ["cancel", "/cancel", "back", "abort"]:
            if user_state != "idle":
                lang = await ctx.db.get_user_language(from_number)
                await ctx.db.set_user_state(from_number, "idle")
                await ctx.wa.send_text_message(from_number, get_text(lang, "process_cancelled"))
                await handle_main_menu(ctx, from_number)
                return

        if user_state == "checkout_pending" and incoming_text:
            await handle_process_checkout(ctx, from_number, incoming_text)
            return

        if user_state == "size_height" and incoming_text:
            await handle_size_rec_height(ctx, from_number, incoming_text)
            return

        if user_state.startswith("size_weight|") and incoming_text:
            height = user_state.split("|", 1)[1]
            await handle_size_rec_weight(ctx, from_number, height, incoming_text)
            return

        if user_state == "waiting_for_cancel_id" and incoming_text:
            await handle_cancel_order_request(ctx, from_number, incoming_text)
            return

        if action_id:
            logger.info(f"Processing action '{action_id}' from {from_number}")
            if not await route_action(ctx, from_number, action_id):
                lang = await ctx.db.get_user_language(from_number)
                await ctx.wa.send_text_message(from_number, get_text(lang, "action_not_recognized"))
                await handle_main_menu(ctx, from_number)

        elif incoming_text:
            logger.info(f"Processing text message from {from_number}")
            await route_text(ctx, from_number, incoming_text)

        # Mark pending message as completed
        if pending_id:
            asyncio.create_task(ctx.db.mark_pending_completed(pending_id))

    except Exception as e:
        logger.error(f"Error handling WhatsApp message: {e}", exc_info=True)
        # Mark pending message as failed
        if pending_id:
            asyncio.create_task(ctx.db.mark_pending_completed(pending_id, error=str(e)[:500]))
        try:
            lang = await ctx.db.get_user_language(from_number)
            await ctx.wa.send_text_message(from_number, get_text(lang, "unknown_error"))
            await handle_main_menu(ctx, from_number)
        except Exception as send_err:
            logger.error(f"Failed to send error message to {from_number}: {send_err}")
