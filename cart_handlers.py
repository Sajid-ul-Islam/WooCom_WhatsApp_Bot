import logging
from context import BotContext
from i18n import get_text, format_text
from shopping_handlers import handle_show_variations

logger = logging.getLogger(__name__)


async def handle_add_to_cart(ctx: BotContext, to: str, product_id: int, quantity: int = 1):
    """Adds a simple (non-variable) product to the user's Supabase cart."""
    lang = await ctx.db.get_user_language(to)
    product = await ctx.wc.get_product(product_id)
    if not product:
        await ctx.wa.send_text_message(to, get_text(lang, "product_unavailable"))
        return

    # If product is variable, route to size selection instead
    if product.get("type") == "variable":
        await handle_show_variations(ctx, to, product_id)
        return

    images = product.get("images", [])
    image_url = images[0].get("src") if images else ""

    await ctx.db.add_to_cart(
        phone_number=to,
        product_id=product_id,
        name=product.get("name", ""),
        price=product.get("price"),
        quantity=quantity,
        image_url=image_url
    )

    text = format_text(lang, "item_added", product_name=product.get('name', ''))
    buttons = [
        {"id": "menu_cart", "title": get_text(lang, "btn_view_cart")},
        {"id": "menu_categories", "title": get_text(lang, "btn_browse_more")},
        {"id": "menu_main", "title": get_text(lang, "btn_main_menu")}
    ]
    await ctx.wa.send_reply_buttons(to, text, buttons)


async def handle_add_variation_to_cart(ctx: BotContext, to: str, product_id: int, variation_id: int):
    """Adds a specific variation (size) of a product to the user's cart."""
    lang = await ctx.db.get_user_language(to)
    # Get parent product for name and image
    product = await ctx.wc.get_product(product_id)
    if not product:
        await ctx.wa.send_text_message(to, get_text(lang, "product_unavailable"))
        return

    # Get the specific variation for its price and attribute details
    variation = await ctx.wc.get_product_variation(product_id, variation_id)
    if not variation:
        await ctx.wa.send_text_message(to, get_text(lang, "size_unavailable"))
        return

    # Extract the size name from variation attributes
    size_name = ""
    for attr in variation.get("attributes", []):
        if "size" in attr.get("name", "").lower():
            size_name = attr.get("option", "")
            break
            
    if not size_name and variation.get("attributes"):
        size_name = " / ".join(str(a.get("option", "")) for a in variation.get("attributes") if a.get("option"))
        
    if not size_name:
        size_name = "Standard"

    # Use variation price if available, otherwise fall back to parent product price
    var_price = variation.get("price") or product.get("price")
    product_name = product.get("name", "")
    full_name = f"{product_name} ({size_name})"

    images = product.get("images", [])
    image_url = images[0].get("src") if images else ""

    await ctx.db.add_to_cart(
        phone_number=to,
        product_id=product_id,
        variation_id=variation_id,
        variation_name=f"Size: {size_name}",
        name=full_name,
        price=var_price,
        quantity=1,
        image_url=image_url
    )

    text = format_text(lang, "variation_added", product_name=full_name)
    buttons = [
        {"id": "menu_cart", "title": get_text(lang, "btn_view_cart")},
        {"id": "menu_categories", "title": get_text(lang, "btn_browse_more")},
        {"id": "menu_main", "title": get_text(lang, "btn_main_menu")}
    ]
    await ctx.wa.send_reply_buttons(to, text, buttons)


async def handle_remove_from_cart(ctx: BotContext, to: str, product_id: int):
    """Removes a product from the user's cart and shows updated cart."""
    lang = await ctx.db.get_user_language(to)
    await ctx.db.remove_from_cart(to, product_id)
    await ctx.wa.send_text_message(to, format_text(lang, "item_removed", product_id=product_id))
    await handle_view_cart(ctx, to)


async def handle_view_cart(ctx: BotContext, to: str):
    """Displays the user's current shopping cart and actions."""
    lang = await ctx.db.get_user_language(to)
    cart_items = await ctx.db.get_cart(to)
    if not cart_items:
        text = get_text(lang, "cart_empty_shop")
        buttons = [
            {"id": "menu_categories", "title": get_text(lang, "btn_browse_catalog")},
            {"id": "menu_main", "title": get_text(lang, "btn_main_menu")}
        ]
        await ctx.wa.send_reply_buttons(to, text, buttons)
        return

    cart_text = get_text(lang, "cart_summary") + "\n\n"
    total = 0.0
    for item in cart_items:
        subtotal = item["price"] * item["quantity"]
        total += subtotal
        cart_text += (
            f"• *{item['name']}* x{item['quantity']}\n"
            f"  {get_text(lang, 'cart_item_price')}: BDT {item['price']:.2f} ({get_text(lang, 'cart_item_subtotal')}: BDT {subtotal:.2f})\n"
            f"  {format_text(lang, 'cart_remove_hint', product_id=item['product_id'])}\n\n"
        )

    cart_text += f"*{get_text(lang, 'cart_total')}: BDT {total:.2f}*"

    buttons = [
        {"id": "cart_checkout", "title": get_text(lang, "cart_checkout")},
        {"id": "cart_clear", "title": get_text(lang, "cart_clear")},
        {"id": "menu_main", "title": get_text(lang, "btn_main_menu")}
    ]
    await ctx.wa.send_reply_buttons(to, cart_text, buttons)


async def handle_checkout_prompt(ctx: BotContext, to: str):
    """Instructs the user on how to complete their checkout and sets state."""
    lang = await ctx.db.get_user_language(to)
    cart_items = await ctx.db.get_cart(to)
    if not cart_items:
        await ctx.wa.send_text_message(to, get_text(lang, "no_items_to_checkout"))
        return

    await ctx.db.set_user_state(to, "checkout_pending")
    await ctx.wa.send_text_message(to, get_text(lang, "checkout_instruction"))


async def handle_process_checkout(ctx: BotContext, to: str, text: str):
    """Parses name and address, then prompts customer for COD order confirmation."""
    lang = await ctx.db.get_user_language(to)
    try:
        parts = text.split(",", 1)
        if len(parts) < 2:
            raise ValueError()
        name = parts[0].strip()
        address = parts[1].strip()
        if not name or not address:
            raise ValueError()
    except (ValueError, IndexError):
        await ctx.wa.send_text_message(to, get_text(lang, "checkout_invalid_format"))
        return

    # Check cart is not empty
    cart_items = await ctx.db.get_cart(to)
    if not cart_items:
        await ctx.db.set_user_state(to, "idle")
        await ctx.wa.send_text_message(to, get_text(lang, "cart_empty_shop_start"))
        return

    # Calculate total for display
    total = sum(item["price"] * item["quantity"] for item in cart_items)

    # Transition to confirmation state, serializing the name and address
    confirm_state = f"checkout_confirm|{name}|{address}"
    await ctx.db.set_user_state(to, confirm_state)

    confirm_text = (
        get_text(lang, "checkout_confirm_title")
        + format_text(lang, "checkout_confirm_fields", name=name, address=address, total=total)
    )

    buttons = [
        {"id": "checkout_place", "title": get_text(lang, "btn_confirm_order")},
        {"id": "checkout_cancel", "title": get_text(lang, "btn_cancel")}
    ]
    await ctx.wa.send_reply_buttons(to, confirm_text, buttons)


async def handle_place_order(ctx: BotContext, to: str, name: str, address: str):
    """Actually places the order in WooCommerce after customer confirmation."""
    lang = await ctx.db.get_user_language(to)
    cart_items = await ctx.db.get_cart(to)
    if not cart_items:
        await ctx.db.set_user_state(to, "idle")
        await ctx.wa.send_text_message(to, get_text(lang, "cart_empty_shop_start"))
        return

    await ctx.wa.send_text_message(to, get_text(lang, "checkout_placing"))

    order = await ctx.wc.create_order(
        phone_number=to,
        customer_name=name,
        cart_items=cart_items,
        address_text=address
    )

    # Reset state
    await ctx.db.set_user_state(to, "idle")

    if not order:
        await ctx.wa.send_text_message(to, get_text(lang, "checkout_failed"))
        return

    await ctx.wc.create_order_note(order.get('id'), "Order placed by customer via WhatsApp Bot.")
    await ctx.db.cache_orders([order], to)
    await ctx.db.clear_cart(to)

    success_text = format_text(lang, "checkout_success",
        order_id=order.get('id'),
        total=order.get('total'),
        payment_method=order.get('payment_method_title'),
        address=address,
    )
    buttons = [
        {"id": "menu_orders", "title": get_text(lang, "btn_view_orders")},
        {"id": "menu_main", "title": get_text(lang, "btn_main_menu")}
    ]
    await ctx.wa.send_reply_buttons(to, success_text, buttons)


async def handle_clear_cart(ctx: BotContext, to: str):
    """Clears the shopping cart."""
    lang = await ctx.db.get_user_language(to)
    await ctx.db.clear_cart(to)
    buttons = [
        {"id": "menu_categories", "title": get_text(lang, "btn_browse_catalog")},
        {"id": "menu_main", "title": get_text(lang, "btn_main_menu")}
    ]
    await ctx.wa.send_reply_buttons(to, get_text(lang, "cart_cleared"), buttons)
