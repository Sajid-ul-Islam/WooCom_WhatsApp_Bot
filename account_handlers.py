import logging
from context import BotContext
from utils import normalize_phone, parse_height, parse_weight, recommend_size
from shopping_handlers import handle_main_menu

logger = logging.getLogger(__name__)


async def handle_view_orders(ctx: BotContext, to: str):
    """Displays order history and status cached locally."""
    live_orders = await ctx.wc.get_orders_by_phone(to)
    if live_orders:
        await ctx.db.cache_orders(live_orders, to)

    orders = await ctx.db.get_cached_orders(to)
    if not orders:
        text = "You haven't placed any orders with this phone number yet."
        buttons = [
            {"id": "menu_categories", "title": "Start Shopping"},
            {"id": "menu_main", "title": "🏠 Main Menu"}
        ]
        await ctx.wa.send_reply_buttons(to, text, buttons)
        return

    order_text = "📦 *Your Recent Orders:*\n\n"
    for o in orders[:5]:
        items_desc = ", ".join([f"{item['name']} (x{item['quantity']})" for item in o.get("items", [])])
        date_str = o.get("created_at")[:10] if o.get("created_at") else "N/A"
        order_text += (
            f"• *Order #{o['id']}* - {date_str}\n"
            f"  Status: *{o['status'].upper()}*\n"
            f"  Items: {items_desc}\n"
            f"  Total: ${o['total']:.2f}\n\n"
        )

    buttons = [{"id": "menu_main", "title": "🏠 Main Menu"}]
    await ctx.wa.send_reply_buttons(to, order_text, buttons)


async def handle_size_rec_start(ctx: BotContext, to: str):
    """Starts the sizing recommendation assistant flow."""
    await ctx.db.set_user_state(to, "size_height")
    await ctx.wa.send_text_message(
        to,
        "📏 *Size Assistant*\n\n"
        "Let's find your perfect size! Please reply with your *height* (e.g., _5'6\"_ or _170 cm_):\n\n"
        "Type *cancel* to abort."
    )


async def handle_size_rec_height(ctx: BotContext, to: str, height_str: str):
    """Records the height and prompts the user for their weight."""
    height = height_str.strip()
    await ctx.db.set_user_state(to, f"size_weight|{height}")
    await ctx.wa.send_text_message(
        to,
        f"Recorded Height: *{height}*.\n\n"
        f"Now please reply with your *weight* (e.g., _65 kg_ or _140 lbs_):\n\n"
        f"Type *cancel* to abort."
    )


async def handle_size_rec_weight(ctx: BotContext, to: str, height_str: str, weight_str: str):
    """Processes weight input, runs the deterministic sizing engine, and displays the recommendation."""
    await ctx.db.set_user_state(to, "idle")
    
    height_inches = parse_height(height_str)
    weight_kg = parse_weight(weight_str)
    
    if height_inches is None or weight_kg is None:
        logger.info(f"Deterministic parsing failed for height '{height_str}' or weight '{weight_str}'. Falling back to AI search.")
        from shopping_handlers import handle_ai_search
        await handle_ai_search(ctx, to, f"What size should I wear? Height: {height_str}, Weight: {weight_str}.")
        return

    rec = recommend_size(height_inches, weight_kg)
    msg = (
        f"📏 *Size Recommendation Results*\n\n"
        f"Recommended Size: *{rec['size']}* (Chest: {rec['chest']})\n"
        f"Confidence Level: *{rec['confidence']}*\n\n"
        f"📝 *Fit Notes:*\n{rec['fit_notes']}\n\n"
        f"🚚 *Delivery Policy:*\n"
        f"• Inside Dhaka: 80 BDT (2-3 days)\n"
        f"• Outside Dhaka: 150 BDT (3-5 days)\n"
        f"• Cash on Delivery (COD) is available nationwide."
    )
    
    buttons = [
        {"id": "menu_categories", "title": "Browse Products"},
        {"id": "menu_main", "title": "🏠 Main Menu"}
    ]
    await ctx.wa.send_reply_buttons(to, msg, buttons)


async def handle_cancel_order_request(ctx: BotContext, to: str, order_id_str: str = ""):
    """Initiates the order cancellation process."""
    if not order_id_str:
        await ctx.db.set_user_state(to, "waiting_for_cancel_id")
        await ctx.wa.send_text_message(
            to,
            "❌ *Order Cancellation*\n\n"
            "Please reply with the Order ID you wish to cancel (e.g. _10254_):\n\n"
            "Type *cancel* to go back."
        )
        return

    try:
        order_id = int(order_id_str.strip())
    except ValueError:
        await ctx.wa.send_text_message(to, "⚠️ Invalid Order ID. Please reply with a valid numeric Order ID:")
        return

    await ctx.wa.send_text_message(to, f"🔍 Looking up order #{order_id}...")
    order = await ctx.wc.get_order(order_id)

    if not order:
        await ctx.db.set_user_state(to, "idle")
        await ctx.wa.send_text_message(to, f"❌ We couldn't find order #{order_id} in our store.")
        return

    # Check ownership (match last 10 digits of billing phone)
    billing_phone = order.get("billing", {}).get("phone", "")
    bp_clean = normalize_phone(billing_phone)
    to_clean = normalize_phone(to)

    if not bp_clean or to_clean[-10:] != bp_clean[-10:]:
        await ctx.db.set_user_state(to, "idle")
        await ctx.wa.send_text_message(
            to,
            "⚠️ Security Check Failed.\n\n"
            "For security reasons, you can only cancel orders placed using this phone number."
        )
        return

    status = order.get("status", "").lower()
    if status not in ["pending", "on-hold", "processing"]:
        await ctx.db.set_user_state(to, "idle")
        await ctx.wa.send_text_message(
            to,
            f"⚠️ Cancellation Not Possible.\n\n"
            f"Order #{order_id} is currently *{status.upper()}*. "
            "Only orders that are pending or processing can be cancelled automatically. "
            "Please contact a human agent if you need assistance."
        )
        return

    # Ask for confirmation
    confirm_text = (
        f"❓ *Confirm Cancellation*\n\n"
        f"Are you sure you want to cancel order *#{order_id}*?"
    )
    buttons = [
        {"id": f"order_cancel_confirm_{order_id}", "title": "Yes, Cancel Order"},
        {"id": "order_cancel_keep", "title": "No, Keep Order"}
    ]
    await ctx.wa.send_reply_buttons(to, confirm_text, buttons)


async def handle_cancel_order_confirm(ctx: BotContext, to: str, order_id: int):
    """Processes order cancellation in WooCommerce and notifies customer."""
    await ctx.wa.send_text_message(to, f"⏳ Cancelling order #{order_id}...")
    success = await ctx.wc.update_order_status(order_id, "cancelled")
    
    await ctx.db.set_user_state(to, "idle")

    if not success:
        await ctx.wa.send_text_message(to, "❌ Failed to cancel the order. Please try again or contact support.")
        return

    await ctx.wc.create_order_note(order_id, "Order cancelled by customer via WhatsApp Bot.")
    
    # Update cache if it exists
    live_orders = await ctx.wc.get_orders_by_phone(to)
    if live_orders:
        await ctx.db.cache_orders(live_orders, to)

    msg = f"✅ *Order #{order_id} has been cancelled.*\n\nThank you. We hope to serve you again in the future!"
    buttons = [{"id": "menu_main", "title": "🏠 Main Menu"}]
    await ctx.wa.send_reply_buttons(to, msg, buttons)


async def handle_cancel_order_keep(ctx: BotContext, to: str):
    """Aborts order cancellation."""
    await ctx.db.set_user_state(to, "idle")
    buttons = [{"id": "menu_main", "title": "🏠 Main Menu"}]
    await ctx.wa.send_reply_buttons(to, "Order cancellation aborted. Your order is safe! 👍", buttons)


async def handle_change_language(ctx: BotContext, to: str):
    """Toggles language between en and bn."""
    lang = await ctx.db.get_user_language(to)
    new_lang = "bn" if lang == "en" else "en"
    await ctx.db.set_user_language(to, new_lang)
    await handle_main_menu(ctx, to)
