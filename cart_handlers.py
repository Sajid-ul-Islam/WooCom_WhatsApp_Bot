import logging
from context import BotContext
from shopping_handlers import handle_show_variations

logger = logging.getLogger(__name__)


async def handle_add_to_cart(ctx: BotContext, to: str, product_id: int, quantity: int = 1):
    """Adds a simple (non-variable) product to the user's Supabase cart."""
    product = await ctx.wc.get_product(product_id)
    if not product:
        await ctx.wa.send_text_message(to, "Sorry, that product is no longer available.")
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

    text = f"✅ *{product.get('name')}* has been added to your cart!"
    buttons = [
        {"id": "menu_cart", "title": "🛍️ View Cart"},
        {"id": "menu_categories", "title": "Browse More"},
        {"id": "menu_main", "title": "🏠 Main Menu"}
    ]
    await ctx.wa.send_reply_buttons(to, text, buttons)


async def handle_add_variation_to_cart(ctx: BotContext, to: str, product_id: int, variation_id: int):
    """Adds a specific variation (size) of a product to the user's cart."""
    # Get parent product for name and image
    product = await ctx.wc.get_product(product_id)
    if not product:
        await ctx.wa.send_text_message(to, "Sorry, that product is no longer available.")
        return

    # Get the specific variation for its price and attribute details
    variation = await ctx.wc.get_product_variation(product_id, variation_id)
    if not variation:
        await ctx.wa.send_text_message(to, "Sorry, that size option is no longer available.")
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

    text = f"✅ *{full_name}* has been added to your cart!"
    buttons = [
        {"id": "menu_cart", "title": "🛍️ View Cart"},
        {"id": "menu_categories", "title": "Browse More"},
        {"id": "menu_main", "title": "🏠 Main Menu"}
    ]
    await ctx.wa.send_reply_buttons(to, text, buttons)


async def handle_remove_from_cart(ctx: BotContext, to: str, product_id: int):
    """Removes a product from the user's cart and shows updated cart."""
    await ctx.db.remove_from_cart(to, product_id)
    await ctx.wa.send_text_message(to, f"❌ Removed product #{product_id} from your cart.")
    await handle_view_cart(ctx, to)


async def handle_view_cart(ctx: BotContext, to: str):
    """Displays the user's current shopping cart and actions."""
    cart_items = await ctx.db.get_cart(to)
    if not cart_items:
        text = "Your shopping cart is currently empty! 🛒\n\nBrowse our catalog to add items."
        buttons = [
            {"id": "menu_categories", "title": "Browse Catalog"},
            {"id": "menu_main", "title": "🏠 Main Menu"}
        ]
        await ctx.wa.send_reply_buttons(to, text, buttons)
        return

    cart_text = "🛍️ *Your Shopping Cart:*\n\n"
    total = 0.0
    for item in cart_items:
        subtotal = item["price"] * item["quantity"]
        total += subtotal
        cart_text += (
            f"• *{item['name']}* x{item['quantity']}\n"
            f"  Price: BDT {item['price']:.2f} (Subtotal: BDT {subtotal:.2f})\n"
            f"  Remove: Reply _Remove {item['product_id']}_\n\n"
        )

    cart_text += f"*Total Amount: BDT {total:.2f}*"

    buttons = [
        {"id": "cart_checkout", "title": "💳 Checkout"},
        {"id": "cart_clear", "title": "🗑️ Clear Cart"},
        {"id": "menu_main", "title": "🏠 Main Menu"}
    ]
    await ctx.wa.send_reply_buttons(to, cart_text, buttons)


async def handle_checkout_prompt(ctx: BotContext, to: str):
    """Instructs the user on how to complete their checkout and sets state."""
    cart_items = await ctx.db.get_cart(to)
    if not cart_items:
        await ctx.wa.send_text_message(to, "Your cart is empty. Please add items before checking out.")
        return

    await ctx.db.set_user_state(to, "checkout_pending")

    instruction = (
        "💳 *Checkout Instructions*\n\n"
        "Please reply with your name and shipping address in the following format:\n\n"
        "*Your Full Name, Your Shipping Address*\n\n"
        "Example:\n"
        "_John Doe, 123 Main Street, New York_\n\n"
        "Or type *cancel* to go back."
    )
    await ctx.wa.send_text_message(to, instruction)


async def handle_process_checkout(ctx: BotContext, to: str, text: str):
    """Parses name and address, then prompts customer for COD order confirmation."""
    try:
        parts = text.split(",", 1)
        if len(parts) < 2:
            raise ValueError()
        name = parts[0].strip()
        address = parts[1].strip()
        if not name or not address:
            raise ValueError()
    except (ValueError, IndexError):
        await ctx.wa.send_text_message(
            to,
            "⚠️ Invalid format.\n\nPlease reply like this:\n*Name, Full Address*\n\nOr type *cancel* to go back."
        )
        return

    # Check cart is not empty
    cart_items = await ctx.db.get_cart(to)
    if not cart_items:
        await ctx.db.set_user_state(to, "idle")
        await ctx.wa.send_text_message(to, "Your cart is empty. Browse products to start shopping!")
        return

    # Calculate total for display
    total = sum(item["price"] * item["quantity"] for item in cart_items)

    # Transition to confirmation state, serializing the name and address
    confirm_state = f"checkout_confirm|{name}|{address}"
    await ctx.db.set_user_state(to, confirm_state)

    confirm_text = (
        f"📋 *Confirm your Cash on Delivery (COD) Order*\n\n"
        f"Name: *{name}*\n"
        f"Shipping Address:\n_{address}_\n\n"
        f"Total Amount: *BDT {total:.2f}*\n"
        f"Payment Method: *Cash on Delivery (COD)*\n\n"
        f"Do you want to confirm and place this order?"
    )

    buttons = [
        {"id": "checkout_place", "title": "👍 Confirm Order"},
        {"id": "checkout_cancel", "title": "❌ Cancel"}
    ]
    await ctx.wa.send_reply_buttons(to, confirm_text, buttons)


async def handle_place_order(ctx: BotContext, to: str, name: str, address: str):
    """Actually places the order in WooCommerce after customer confirmation."""
    cart_items = await ctx.db.get_cart(to)
    if not cart_items:
        await ctx.db.set_user_state(to, "idle")
        await ctx.wa.send_text_message(to, "Your cart is empty. Browse products to start shopping!")
        return

    await ctx.wa.send_text_message(to, "⏳ Placing your order, please wait...")

    order = await ctx.wc.create_order(
        phone_number=to,
        customer_name=name,
        cart_items=cart_items,
        address_text=address
    )

    # Reset state
    await ctx.db.set_user_state(to, "idle")

    if not order:
        await ctx.wa.send_text_message(to, "❌ Failed to place order in our system. Please try again later.")
        return

    await ctx.wc.create_order_note(order.get('id'), "Order placed by customer via WhatsApp Bot.")
    await ctx.db.cache_orders([order], to)
    await ctx.db.clear_cart(to)

    success_text = (
        f"🎉 *Order Placed Successfully!*\n\n"
        f"Order ID: *#{order.get('id')}*\n"
        f"Total Amount: *BDT {order.get('total')}*\n"
        f"Payment Method: *{order.get('payment_method_title')}*\n\n"
        f"We will ship your items to:\n_{address}_\n\n"
        f"Thank you for shopping with us!"
    )
    buttons = [
        {"id": "menu_orders", "title": "📦 View Orders"},
        {"id": "menu_main", "title": "🏠 Main Menu"}
    ]
    await ctx.wa.send_reply_buttons(to, success_text, buttons)


async def handle_clear_cart(ctx: BotContext, to: str):
    """Clears the shopping cart."""
    await ctx.db.clear_cart(to)
    buttons = [
        {"id": "menu_categories", "title": "Browse Catalog"},
        {"id": "menu_main", "title": "🏠 Main Menu"}
    ]
    await ctx.wa.send_reply_buttons(to, "🗑️ Your shopping cart has been cleared.", buttons)
