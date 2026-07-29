import logging
from context import BotContext
from utils import normalize_phone, parse_height, parse_weight, recommend_size
from i18n import get_text, format_text
from shopping_handlers import handle_main_menu

logger = logging.getLogger(__name__)


async def handle_view_orders(ctx: BotContext, to: str):
    """Displays order history and status cached locally."""
    live_orders = await ctx.wc.get_orders_by_phone(to)
    if live_orders:
        await ctx.db.cache_orders(live_orders, to)

    lang = await ctx.db.get_user_language(to)
    orders = await ctx.db.get_cached_orders(to)
    if not orders:
        text = get_text(lang, "no_orders")
        buttons = [
            {"id": "menu_categories", "title": get_text(lang, "btn_start_shopping")},
            {"id": "menu_main", "title": get_text(lang, "btn_main_menu")}
        ]
        await ctx.wa.send_reply_buttons(to, text, buttons)
        return

    order_text = get_text(lang, "orders_title")
    for o in orders[:5]:
        items_desc = ", ".join([f"{item['name']} (x{item['quantity']})" for item in o.get("items", [])])
        date_str = o.get("created_at")[:10] if o.get("created_at") else "N/A"
        order_text += format_text(lang, "order_line",
            order_id=o['id'],
            date=date_str,
            status=o['status'].upper(),
            items=items_desc,
            total=o['total'],
        )

    buttons = [{"id": "menu_main", "title": get_text(lang, "btn_main_menu")}]
    await ctx.wa.send_reply_buttons(to, order_text, buttons)


async def handle_size_rec_start(ctx: BotContext, to: str):
    """Starts the sizing recommendation assistant flow."""
    lang = await ctx.db.get_user_language(to)
    await ctx.db.set_user_state(to, "size_height")
    await ctx.wa.send_text_message(to, get_text(lang, "size_assist_title"))


async def handle_size_rec_height(ctx: BotContext, to: str, height_str: str):
    """Records the height and prompts the user for their weight."""
    lang = await ctx.db.get_user_language(to)
    height = height_str.strip()
    await ctx.db.set_user_state(to, f"size_weight|{height}")
    await ctx.wa.send_text_message(to, format_text(lang, "size_height_prompt", height=height))


async def handle_size_rec_weight(ctx: BotContext, to: str, height_str: str, weight_str: str):
    """Processes weight input, runs the deterministic sizing engine, and displays the recommendation."""
    lang = await ctx.db.get_user_language(to)
    await ctx.db.set_user_state(to, "idle")
    
    height_inches = parse_height(height_str)
    weight_kg = parse_weight(weight_str)
    
    if height_inches is None or weight_kg is None:
        logger.info(f"Deterministic parsing failed for height '{height_str}' or weight '{weight_str}'. Falling back to AI search.")
        from shopping_handlers import handle_ai_search
        await handle_ai_search(ctx, to, f"What size should I wear? Height: {height_str}, Weight: {weight_str}.")
        return

    rec = recommend_size(height_inches, weight_kg)
    msg = format_text(lang, "size_results_title",
        size=rec['size'],
        chest=rec['chest'],
        confidence=rec['confidence'],
        notes=rec['fit_notes'],
    )
    
    buttons = [
        {"id": "menu_categories", "title": get_text(lang, "menu_categories")},
        {"id": "menu_main", "title": get_text(lang, "btn_main_menu")}
    ]
    await ctx.wa.send_reply_buttons(to, msg, buttons)


async def handle_cancel_order_request(ctx: BotContext, to: str, order_id_str: str = ""):
    """Initiates the order cancellation process."""
    lang = await ctx.db.get_user_language(to)
    if not order_id_str:
        await ctx.db.set_user_state(to, "waiting_for_cancel_id")
        await ctx.wa.send_text_message(to, get_text(lang, "cancel_title"))
        return

    try:
        order_id = int(order_id_str.strip())
    except ValueError:
        await ctx.wa.send_text_message(to, get_text(lang, "cancel_invalid_id"))
        return

    await ctx.wa.send_text_message(to, format_text(lang, "order_lookup", order_id=order_id))
    order = await ctx.wc.get_order(order_id)

    if not order:
        await ctx.db.set_user_state(to, "idle")
        await ctx.wa.send_text_message(to, format_text(lang, "order_not_found", order_id=order_id))
        return

    # Check ownership (match last 10 digits of billing phone)
    billing_phone = order.get("billing", {}).get("phone", "")
    bp_clean = normalize_phone(billing_phone)
    to_clean = normalize_phone(to)

    if not bp_clean or to_clean[-10:] != bp_clean[-10:]:
        await ctx.db.set_user_state(to, "idle")
        await ctx.wa.send_text_message(to, get_text(lang, "cancel_security_fail"))
        return

    status = order.get("status", "").lower()
    if status not in ["pending", "on-hold", "processing"]:
        await ctx.db.set_user_state(to, "idle")
        await ctx.wa.send_text_message(to, format_text(lang, "cancel_not_possible", order_id=order_id, status=status.upper()))
        return

    # Ask for confirmation
    confirm_text = format_text(lang, "cancel_confirm_q", order_id=order_id)
    buttons = [
        {"id": f"order_cancel_confirm_{order_id}", "title": get_text(lang, "btn_yes_cancel")},
        {"id": "order_cancel_keep", "title": get_text(lang, "btn_no_keep")}
    ]
    await ctx.wa.send_reply_buttons(to, confirm_text, buttons)


async def handle_cancel_order_confirm(ctx: BotContext, to: str, order_id: int):
    """Processes order cancellation in WooCommerce and notifies customer."""
    lang = await ctx.db.get_user_language(to)
    await ctx.wa.send_text_message(to, format_text(lang, "order_cancelling", order_id=order_id))
    success = await ctx.wc.update_order_status(order_id, "cancelled")
    
    await ctx.db.set_user_state(to, "idle")

    if not success:
        await ctx.wa.send_text_message(to, get_text(lang, "cancel_failed"))
        return

    await ctx.wc.create_order_note(order_id, "Order cancelled by customer via WhatsApp Bot.")
    
    # Update cache if it exists
    live_orders = await ctx.wc.get_orders_by_phone(to)
    if live_orders:
        await ctx.db.cache_orders(live_orders, to)

    msg = format_text(lang, "cancel_success", order_id=order_id)
    buttons = [{"id": "menu_main", "title": get_text(lang, "btn_main_menu")}]
    await ctx.wa.send_reply_buttons(to, msg, buttons)


async def handle_cancel_order_keep(ctx: BotContext, to: str):
    """Aborts order cancellation."""
    lang = await ctx.db.get_user_language(to)
    await ctx.db.set_user_state(to, "idle")
    buttons = [{"id": "menu_main", "title": get_text(lang, "btn_main_menu")}]
    await ctx.wa.send_reply_buttons(to, get_text(lang, "cancel_aborted"), buttons)


async def handle_change_language(ctx: BotContext, to: str):
    """Cycles language: en → bn → blish → en."""
    lang = await ctx.db.get_user_language(to)
    lang_cycle = ["en", "bn", "blish"]
    try:
        idx = lang_cycle.index(lang)
        new_lang = lang_cycle[(idx + 1) % len(lang_cycle)]
    except ValueError:
        new_lang = "en"
    await ctx.db.set_user_language(to, new_lang)
    await handle_main_menu(ctx, to)
