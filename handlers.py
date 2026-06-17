import os
import re
import logging

from context import BotContext
from utils import clean_html

logger = logging.getLogger(__name__)


# ==================== HANDLERS ====================


async def handle_main_menu(ctx: BotContext, to: str):
    """Sends the main menu options using a List Message (supports up to 10 options)."""
    text = (
        "Assalamu Alaikum! 👋\n\n"
        "Welcome to our WooCommerce Store! How can I help you today?\n\n"
        "Please select an option from the menu below, ask me a question about our products, "
        "or search for items directly."
    )

    sections = [{
        "title": "Main Menu Options",
        "rows": [
            {"id": "menu_categories", "title": "🛍️ Browse Categories", "description": "Explore our store's catalog"},
            {"id": "menu_cart", "title": "🛒 View Cart", "description": "Check your selected items"},
            {"id": "menu_orders", "title": "📦 My Orders", "description": "Track your past purchases"},
            {"id": "menu_size", "title": "📏 Size Assistant", "description": "Find your perfect size"},
            {"id": "menu_cancel_order", "title": "❌ Cancel Order", "description": "Cancel a pending order"},
            {"id": "cart_clear", "title": "🗑️ Clear Cart", "description": "Empty your shopping cart"},
            {"id": "menu_human", "title": "🧑‍💻 Talk to Human", "description": "Pause the AI and talk to staff"}
        ]
    }]

    await ctx.wa.send_list_message(
        to=to,
        button_text="Tap for Options",
        body_text=text,
        sections=sections,
        header_text="Main Menu"
    )


async def handle_categories(ctx: BotContext, to: str):
    """Sends product categories to the user as a List Message."""
    categories = await ctx.wc.get_categories()
    if not categories:
        await ctx.wa.send_text_message(to, "Sorry, I couldn't load store categories right now.")
        return

    rows = []
    for cat in categories[:10]:
        rows.append({
            "id": f"cat_{cat['id']}",
            "title": cat["name"],
            "description": f"View products in {cat['name']}"
        })

    sections = [{"title": "Store Categories", "rows": rows}]

    await ctx.wa.send_list_message(
        to=to,
        button_text="Select Category",
        body_text="Choose a category from the list below to view products:",
        sections=sections,
        header_text="Categories"
    )


async def handle_category_products(ctx: BotContext, to: str, category_id: int):
    """Sends products in a specific category as a List Message."""
    products = await ctx.wc.get_products(category_id=category_id, per_page=10)
    if not products:
        await ctx.wa.send_text_message(to, "This category doesn't have any products currently.")
        return

    rows = []
    for p in products:
        price_text = f"${p.get('price')}" if p.get("price") else "Price on request"
        rows.append({
            "id": f"prod_{p['id']}",
            "title": p["name"],
            "description": f"{price_text} - View details"
        })

    sections = [{"title": "Available Products", "rows": rows}]

    await ctx.wa.send_list_message(
        to=to,
        button_text="Select Product",
        body_text="Here are the products in this category. Select one to see details:",
        sections=sections,
        header_text="Category Products"
    )


async def handle_product_detail(ctx: BotContext, to: str, product_id: int):
    """Sends product details, including pricing, description, and image."""
    product = await ctx.wc.get_product(product_id)
    if not product:
        await ctx.wa.send_text_message(to, "Sorry, I couldn't find details for that product.")
        return

    name = product.get("name")
    price = f"${product.get('price')}" if product.get("price") else "Price on request"
    permalink = product.get("permalink", "")

    desc_raw = product.get("description") or product.get("short_description") or "No description available."
    description = clean_html(desc_raw)
    if len(description) > 300:
        description = description[:297] + "..."

    caption = (
        f"*{name}*\n"
        f"Price: *{price}*\n\n"
        f"{description}\n\n"
        f"Link: {permalink}"
    )

    images = product.get("images", [])
    image_url = images[0].get("src") if images else None

    buttons = [
        {"id": f"add_{product_id}", "title": "🛒 Add to Cart"},
        {"id": "menu_cart", "title": "🛍️ View Cart"},
        {"id": "menu_main", "title": "🏠 Main Menu"}
    ]

    if image_url:
        await ctx.wa.send_image_message(to, image_url, caption=caption)
        await ctx.wa.send_reply_buttons(to, "What would you like to do next?", buttons)
    else:
        await ctx.wa.send_reply_buttons(to, caption, buttons)


async def handle_add_to_cart(ctx: BotContext, to: str, product_id: int, quantity: int = 1):
    """Adds a product to the user's Supabase cart and notifies them."""
    product = await ctx.wc.get_product(product_id)
    if not product:
        await ctx.wa.send_text_message(to, "Sorry, that product is no longer available.")
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
            f"  Price: ${item['price']:.2f} (Subtotal: ${subtotal:.2f})\n"
            f"  Remove: Reply _Remove {item['product_id']}_\n\n"
        )

    cart_text += f"*Total Amount: ${total:.2f}*"

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
    except Exception:
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
        f"Total Amount: *${total:.2f}*\n"
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

    await ctx.db.cache_orders([order], to)
    await ctx.db.clear_cart(to)

    success_text = (
        f"🎉 *Order Placed Successfully!*\n\n"
        f"Order ID: *#{order.get('id')}*\n"
        f"Total Amount: *${order.get('total')}*\n"
        f"Payment Method: *{order.get('payment_method_title')}*\n\n"
        f"We will ship your items to:\n_{address}_\n\n"
        f"Thank you for shopping with us!"
    )
    buttons = [
        {"id": "menu_orders", "title": "📦 View Orders"},
        {"id": "menu_main", "title": "🏠 Main Menu"}
    ]
    await ctx.wa.send_reply_buttons(to, success_text, buttons)


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


async def handle_clear_cart(ctx: BotContext, to: str):
    """Clears the shopping cart."""
    await ctx.db.clear_cart(to)
    buttons = [
        {"id": "menu_categories", "title": "Browse Catalog"},
        {"id": "menu_main", "title": "🏠 Main Menu"}
    ]
    await ctx.wa.send_reply_buttons(to, "🗑️ Your shopping cart has been cleared.", buttons)


async def handle_human_agent(ctx: BotContext, to: str):
    """Pauses the bot and provides a link to contact a human agent."""
    await ctx.db.set_bot_paused(to, True)
    agent_phone = os.getenv("HUMAN_AGENT_PHONE", "1234567890")
    msg = (
        "⏸️ I have paused my automated responses.\n\n"
        f"Please click this link to chat directly with our human agent on WhatsApp:\n👉 https://wa.me/{agent_phone}\n\n"
        "Type */resume* when you want me to take over again."
    )
    await ctx.wa.send_text_message(to, msg)


async def handle_ai_search(ctx: BotContext, to: str, query: str):
    """Passes user text query to the RAG Agent and returns LLM and matching products."""
    await ctx.wa.send_text_message(to, "🔍 Searching the catalog, please wait...")

    history = await ctx.db.get_user_history(to)
    orders = await ctx.db.get_cached_orders(to)

    result = await ctx.agent.answer_query(query, history=history, orders=orders)
    sentiment = result.get("sentiment", "neutral")

    # Sentiment auto-escalation
    if sentiment in ["frustrated", "angry"]:
        logger.info(f"Auto-escalating user {to} due to {sentiment} sentiment.")
        escalation_msg = (
            "⚠️ *Human Agent Escalation*\n\n"
            "I detect that you are frustrated or need urgent assistance. "
            "I am pausing my automated responses and transferring you to our human support team."
        )
        await ctx.wa.send_text_message(to, escalation_msg)
        await handle_human_agent(ctx, to)
        return

    response_text = result["text"]
    matching_products = result["products"]

    history.append({"role": "user", "content": query})
    history.append({"role": "assistant", "content": response_text})
    history = history[-10:]  # keep last 10 messages
    await ctx.db.update_user_history(to, history)

    await ctx.wa.send_text_message(to, response_text)

    if matching_products:
        rows = []
        for p in matching_products:
            price_text = f"${p.get('price')}" if p.get("price") else "Price on request"
            rows.append({
                "id": f"prod_{p['id']}",
                "title": p["name"],
                "description": f"{price_text} - View details"
            })
        sections = [{"title": "Recommended Items", "rows": rows}]
        await ctx.wa.send_list_message(
            to=to,
            button_text="View Match",
            body_text="Click below to see the specifications, photos or add recommended products to cart:",
            sections=sections,
            header_text="Matching Results"
        )
    else:
        buttons = [
            {"id": "menu_categories", "title": "Browse Categories"},
            {"id": "menu_main", "title": "🏠 Main Menu"}
        ]
        await ctx.wa.send_reply_buttons(to, "What would you like to do?", buttons)


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
    "menu_cancel_order": lambda ctx, to: handle_cancel_order_request(ctx, to, ""),
}

PREFIX_HANDLERS = [
    ("cat_", handle_category_products),
    ("prod_", handle_product_detail),
    ("add_", handle_add_to_cart),
    ("rmv_", handle_remove_from_cart),
    ("order_cancel_confirm_", lambda ctx, to, order_id: handle_cancel_order_confirm(ctx, to, order_id)),
]

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
        await ctx.wa.send_text_message(to, "❌ Session expired. Checkout cancelled.")
        await handle_main_menu(ctx, to)
        return True

    if action_id == "checkout_cancel":
        await ctx.db.set_user_state(to, "idle")
        await ctx.wa.send_text_message(to, "Order checkout cancelled.")
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

    # Prefix match (e.g. "cat_123" -> handle_category_products(ctx, to, 123))
    for prefix, handler in PREFIX_HANDLERS:
        if action_id.startswith(prefix):
            id_str = action_id[len(prefix):]
            await handler(ctx, to, int(id_str))
            return True

    return False


async def route_text(ctx: BotContext, to: str, text: str):
    """Route a text message to the appropriate handler."""
    text_lower = text.lower().strip()

    # Exact keyword match
    if text_lower in TEXT_COMMANDS:
        await TEXT_COMMANDS[text_lower](ctx, to)
        return

    # Regex: "cancel order 12345"
    cancel_match = re.match(r"^cancel\s+order\s+(\d+)", text_lower)
    if cancel_match:
        await handle_cancel_order_request(ctx, to, cancel_match.group(1))
        return

    # Regex: "Add 123"
    add_match = re.match(r"^add\s+(\d+)", text_lower)
    if add_match:
        try:
            await handle_add_to_cart(ctx, to, int(add_match.group(1)))
        except Exception:
            await ctx.wa.send_text_message(
                to, "To add a product, please type *Add [Product ID]* (e.g. *Add 105*)."
            )
        return

    # Regex: "Remove 123"
    remove_match = re.match(r"^remove\s+(\d+)", text_lower)
    if remove_match:
        try:
            await handle_remove_from_cart(ctx, to, int(remove_match.group(1)))
        except Exception:
            await ctx.wa.send_text_message(
                to, "To remove an item, type *Remove [Product ID]* (e.g. *Remove 105*)."
            )
        return

    # Legacy checkout command (still supported)
    if text_lower.startswith("checkout:"):
        details_text = text.split(":", 1)[1].strip()
        await handle_process_checkout(ctx, to, details_text)
        return

    # Default: AI search/QA query
    await handle_ai_search(ctx, to, text)


# ==================== MESSAGE PROCESSING ====================


async def process_incoming_message(
    ctx: BotContext, from_number: str, message: dict,
    value: dict, action_id: str, incoming_text: str
):
    """Processes WhatsApp message in the background to avoid blocking response to Meta."""
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
                await ctx.wa.send_text_message(from_number, "✅ Bot resumed. How can I help you?")
                return

        is_paused = await ctx.db.is_bot_paused(from_number)
        if is_paused:
            logger.info(f"Bot paused for {from_number}. Ignoring message.")
            return

        # --- State machine checking ---
        user_state = await ctx.db.get_user_state(from_number)

        if incoming_text and incoming_text.lower() in ["cancel", "/cancel", "back", "abort"]:
            if user_state != "idle":
                await ctx.db.set_user_state(from_number, "idle")
                await ctx.wa.send_text_message(from_number, "❌ Process cancelled.")
                await handle_main_menu(ctx, from_number)
                return

        if user_state == "checkout_pending" and incoming_text:
            await handle_process_checkout(ctx, from_number, incoming_text)
            return

        if user_state == "size_height" and incoming_text:
            height = incoming_text.strip()
            await ctx.db.set_user_state(from_number, f"size_weight|{height}")
            await ctx.wa.send_text_message(
                from_number,
                f"Recorded Height: *{height}*.\n\n"
                f"Now please reply with your *weight* (e.g., _65 kg_ or _140 lbs_):\n\n"
                f"Type *cancel* to abort."
            )
            return

        if user_state.startswith("size_weight|") and incoming_text:
            height = user_state.split("|", 1)[1]
            weight = incoming_text.strip()
            await ctx.db.set_user_state(from_number, "idle")
            # Ask AI sizing query
            await handle_ai_search(
                ctx, from_number,
                f"What size should I wear? Height: {height}, Weight: {weight}."
            )
            return

        if user_state == "waiting_for_cancel_id" and incoming_text:
            await handle_cancel_order_request(ctx, from_number, incoming_text)
            return

        if action_id:
            logger.info(f"Processing action '{action_id}' from {from_number}")
            if not await route_action(ctx, from_number, action_id):
                await ctx.wa.send_text_message(from_number, "I didn't recognize that action. Returning to main menu.")
                await handle_main_menu(ctx, from_number)

        elif incoming_text:
            logger.info(f"Processing text message from {from_number}")
            await route_text(ctx, from_number, incoming_text)

    except Exception as e:
        logger.error(f"Error handling WhatsApp message: {e}", exc_info=True)
        try:
            await ctx.wa.send_text_message(from_number, "Sorry, I had trouble processing that action. Returning to main menu.")
            await handle_main_menu(ctx, from_number)
        except Exception:
            pass
