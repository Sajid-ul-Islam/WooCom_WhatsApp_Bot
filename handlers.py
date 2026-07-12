import os
import re
import asyncio
import logging

from context import BotContext
from utils import clean_html
from i18n import get_text

logger = logging.getLogger(__name__)


# ==================== HANDLERS ====================


async def handle_main_menu(ctx: BotContext, to: str):
    """Sends a dynamic, modern main menu based on user state."""
    # Fetch dynamic user state (cart items)
    cart = await ctx.db.get_cart(to)
    cart_items = sum(item.get("quantity", 1) for item in cart)
    lang = await ctx.db.get_user_language(to)

    text = get_text(lang, "welcome")

    # 1. Shopping Section
    shopping_rows = [
        {"id": "menu_categories", "title": get_text(lang, "menu_categories"), "description": "Explore our collections and special offers"},
        {"id": "menu_recommend", "title": get_text(lang, "menu_recommend"), "description": "Products selected just for you based on your history"}
    ]
    
    if cart_items > 0:
        shopping_rows.append({
            "id": "menu_cart", 
            "title": f"🛒 ({cart_items}) {get_text(lang, 'menu_cart')}", 
            "description": "You have items waiting! Ready to checkout?"
        })
    else:
        shopping_rows.append({
            "id": "menu_cart", 
            "title": get_text(lang, "menu_cart"), 
            "description": "Your cart is currently empty"
        })
        
    shopping_rows.append({
        "id": "menu_size", 
        "title": get_text(lang, "menu_size"), 
        "description": "Find your perfect fit instantly"
    })

    # 2. Account Section
    account_rows = [
        {"id": "menu_orders", "title": get_text(lang, "menu_orders"), "description": "View your recent purchases and status"}
    ]
    
    # 3. Support & Settings Section
    support_rows = [
        {"id": "menu_cancel_order", "title": "❌ Cancel Order", "description": "Request a cancellation for a recent order"},
        {"id": "menu_human", "title": get_text(lang, "menu_human"), "description": "Pause the AI and chat with a real human"},
        {"id": "menu_language", "title": get_text(lang, "menu_language"), "description": "English / বাংলা"}
    ]
    
    if cart_items > 0:
        support_rows.append({
            "id": "cart_clear", 
            "title": get_text(lang, "cart_clear"), 
            "description": "Empty all items from your cart"
        })

    sections = [
        {"title": "🛍️ Store", "rows": shopping_rows},
        {"title": "👤 Account", "rows": account_rows},
        {"title": "📞 Support", "rows": support_rows}
    ]

    await ctx.wa.send_list_message(
        to=to,
        button_text="☰ Open Menu",
        body_text=text,
        sections=sections,
        header_text="DEEN Commerce"
    )


async def handle_categories(ctx: BotContext, to: str):
    """Sends product categories to the user as a List Message, split into Promos, Men's, and Others."""
    # Fetch top-level categories (for promos and others) and MEN's subcategories (for regular items)
    top_categories = await ctx.wc.get_categories(parent=0)
    men_categories = await ctx.wc.get_categories(parent=508)
    
    if not top_categories and not men_categories:
        await ctx.wa.send_text_message(to, "Sorry, I couldn't load store categories right now.")
        return

    promo_keywords = ["sale", "new", "off", "bogo", "discount", "%", "offer", "clearance", "bundle", "value"]
    promo_rows = []
    mens_rows = []
    other_rows = []

    # Extract promos and other top-level categories
    for cat in top_categories:
        if cat["name"].lower() == "uncategorized":
            continue
        name_lower = cat["name"].lower()
        is_promo = any(kw in name_lower for kw in promo_keywords)
        if is_promo:
            promo_rows.append({
                "id": f"cat_{cat['id']}",
                "title": cat["name"][:24],
                "description": f"View products in {cat['name']}"[:72]
            })
        elif cat["id"] != 508:  # Skip MEN top level since we show its subcategories
            other_rows.append({
                "id": f"cat_{cat['id']}",
                "title": cat["name"][:24],
                "description": f"View products in {cat['name']}"[:72]
            })

    # Extract regular categories from MEN (id: 508)
    for cat in men_categories:
        mens_rows.append({
            "id": f"cat_{cat['id']}",
            "title": cat["name"][:24],
            "description": f"View products in {cat['name']}"[:72]
        })

    # WhatsApp allows max 10 rows total across all sections
    final_promo = promo_rows[:3]
    final_mens = mens_rows[:4]
    final_other = other_rows[:(10 - len(final_promo) - len(final_mens))]

    sections = []
    if final_promo:
        sections.append({"title": "🔥 Special Offers", "rows": final_promo})
    if final_mens:
        sections.append({"title": "🛍️ Men's Collection", "rows": final_mens})
    if final_other:
        sections.append({"title": "✨ Other Categories", "rows": final_other})

    lang = await ctx.db.get_user_language(to)
    from i18n import get_text
    
    await ctx.wa.send_list_message(
        to=to,
        button_text=get_text(lang, "categories_btn"),
        body_text=get_text(lang, "categories_body"),
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
        price_text = f"BDT {p.get('price')}" if p.get("price") else "Price on request"
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
    """Sends product details dynamically, extracting precise pricing, stock, and metadata.
    Detects if product has variations (e.g. sizes) and adjusts buttons accordingly."""
    product = await ctx.wc.get_product(product_id)
    if not product:
        await ctx.wa.send_text_message(to, "Sorry, I couldn't find details for that product.")
        return

    name = product.get("name")
    permalink = product.get("permalink", "")
    
    # 1. Precise Pricing
    regular_price = product.get("regular_price")
    sale_price = product.get("sale_price")
    price_val = product.get("price")
    
    if sale_price and regular_price and float(sale_price) < float(regular_price):
        price_display = f"~BDT {regular_price}~ *${sale_price}* (Sale!)"
    elif price_val:
        price_display = f"*BDT {price_val}*"
    else:
        price_display = "Price on request"

    # 2. Stock Status
    stock_status = product.get("stock_status", "instock")
    if stock_status == "instock":
        stock_display = "✅ In Stock"
        qty = product.get("stock_quantity")
        if qty:
            stock_display += f" ({qty} available)"
    elif stock_status == "outofstock":
        stock_display = "❌ Out of Stock"
    else:
        stock_display = "⏳ On Backorder"
        
    # 3. Categories & Rating
    cats = product.get("categories", [])
    cat_names = ", ".join(c.get("name", "") for c in cats) if cats else "General"
    
    rating = product.get("average_rating", "0.0")
    rating_display = f"⭐ {rating}/5.0" if float(rating) > 0 else "No reviews yet"

    # 4. Clean Description
    desc_raw = product.get("short_description") or product.get("description") or "No description available."
    description = clean_html(desc_raw).strip()
    if len(description) > 200:
        description = description[:197] + "..."

    caption = (
        f"*{name}*\n"
        f"🏷️ Category: {cat_names}\n"
        f"{rating_display}\n\n"
        f"Price: {price_display}\n"
        f"Status: {stock_display}\n\n"
        f"📝 *Details:*\n{description}\n\n"
        f"🔗 Link: {permalink}"
    )

    images = product.get("images", [])
    image_url = images[0].get("src") if images else None

    # Check product type: variable products need size selection before adding to cart
    product_type = product.get("type", "simple")

    if product_type == "variable":
        buttons = [
            {"id": f"size_sel_{product_id}", "title": "📏 Select Size"},
            {"id": f"size_chart_{product_id}", "title": "📐 Size Chart"},
            {"id": "menu_main", "title": "🏠 Main Menu"}
        ]
    else:
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


# ==================== VARIATION / SIZE HANDLERS ====================


async def handle_show_variations(ctx: BotContext, to: str, product_id: int):
    """Shows available size options for a variable product as a selectable list."""
    product = await ctx.wc.get_product(product_id)
    if not product:
        await ctx.wa.send_text_message(to, "Sorry, I couldn't find that product.")
        return

    variations = await ctx.wc.get_product_variations(product_id)
    if not variations:
        await ctx.wa.send_text_message(to, "This product has no available size options at the moment.")
        return

    rows = []
    for v in variations:
        if v.get("status") != "publish":
            continue

        # Extract size attribute value
        size = ""
        for attr in v.get("attributes", []):
            if "size" in attr.get("name", "").lower():
                size = attr.get("option", "")
                break
        
        if not size and v.get("attributes"):
            size = " / ".join(str(a.get("option", "")) for a in v.get("attributes") if a.get("option"))
            
        if not size:
            size = "Standard"

        var_price = v.get("price") or product.get("price") or "0"
        stock_status = v.get("stock_status", "instock")
        in_stock = stock_status != "outofstock"

        price_text = f"BDT {var_price}" if var_price else ""
        rows.append({
            "id": f"varadd_{product_id}_{v['id']}",
            "title": size[:24],
            "description": f"{price_text}" if in_stock else f"{price_text} - Out of Stock"
        })

    if not rows:
        await ctx.wa.send_text_message(to, "No sizes are currently available for this product.")
        return

    sections = [
        {
            "title": "Available Sizes",
            "rows": rows
        },
        {
            "title": "Help",
            "rows": [
                {"id": f"size_chart_{product_id}", "title": "📐 View Size Chart", "description": "See our sizing guide"}
            ]
        }
    ]

    await ctx.wa.send_list_message(
        to=to,
        button_text="Select Size",
        body_text=f"Choose your size for *{product.get('name')}*:",
        sections=sections,
        header_text="Select Size"
    )


async def handle_size_chart(ctx: BotContext, to: str, product_id: int):
    """Shows the sizing guide/chart by extracting an image from the product description."""
    product = await ctx.wc.get_product(product_id)
    image_url = None

    if product:
        # Search for an image in the description or short description
        html_content = product.get("description", "") + " " + product.get("short_description", "")
        import re
        match = re.search(r'<img\s+[^>]*src=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
        if match:
            image_url = match.group(1)

    buttons = [
        {"id": f"size_sel_{product_id}", "title": "📏 Select Size"},
        {"id": "menu_main", "title": "🏠 Main Menu"}
    ]

    if image_url:
        await ctx.wa.send_image_message(to, image_url, caption="📏 *Size Chart*")
        await ctx.wa.send_reply_buttons(to, "Would you like to select a size?", buttons)
    else:
        # Fallback to default size guide if no image is found
        size_guide = (
            "📏 *Size Guide*\n\n"
            "*Panjabis & Shirts:*\n"
            "• S (Small): Height 5'2\"-5'5\", Weight 50-60 kg (Chest: 38\")\n"
            "• M (Medium): Height 5'5\"-5'7\", Weight 60-70 kg (Chest: 40\")\n"
            "• L (Large): Height 5'7\"-5'10\", Weight 70-80 kg (Chest: 42\")\n"
            "• XL (XL): Height 5'10\"-6'0\", Weight 80-90 kg (Chest: 44\")\n"
            "• XXL (2XL): Height 6'0\"+, Weight 90+ kg (Chest: 46\")\n\n"
            "*Delivery:*\n"
            "• Inside Dhaka: 80 BDT, 2-3 days\n"
            "• Outside Dhaka: 150 BDT, 3-5 days\n"
            "• Cash on Delivery (COD) available nationwide.\n\n"
            "Need a personal recommendation? Use the *Size Assistant* from the main menu!"
        )
        await ctx.wa.send_reply_buttons(to, size_guide, buttons)


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
    agent_phone = os.getenv("HUMAN_AGENT_PHONE", "8801952700500")
    msg = (
        "⏸️ I have paused my automated responses.\n\n"
        f"Please click this link to chat directly with our human agent on WhatsApp:\n👉 https://wa.me/{agent_phone}\n\n"
        "Type */resume* when you want me to take over again."
    )
    await ctx.wa.send_text_message(to, msg)


async def handle_ai_search(ctx: BotContext, to: str, query: str):
    """Passes user text query to the RAG Agent and returns LLM and matching products.
    Uses a fast-path fuzzy match to bypass LLM for exact or very close matches."""
    
    # === Fast Path: Direct Fuzzy Match ===
    if ctx.fuzzy and ctx.fuzzy.ready:
        fuzzy_matches = ctx.fuzzy.search(query, max_results=5, min_score=60.0)
        if fuzzy_matches:
            top_match = fuzzy_matches[0]
            top_score = top_match.get("_fuzzy_score", 0.0)
            
            # Excellent match -> Bypass AI and show product directly
            if top_score >= 85.0:
                await handle_product_detail(ctx, to, top_match["id"])
                return
                
            # Good match -> Show list of products directly
            if top_score >= 65.0:
                rows = []
                for p in fuzzy_matches:
                    price_text = f"BDT {p.get('price')}" if p.get("price") else "Price on request"
                    rows.append({
                        "id": f"prod_{p['id']}",
                        "title": p.get("name", "")[:24],
                        "description": f"{price_text} - View details"[:72]
                    })
                sections = [{"title": "Matching Products", "rows": rows}]
                await ctx.wa.send_list_message(
                    to=to,
                    button_text="View Matches",
                    body_text="I found these items based on your search:",
                    sections=sections,
                    header_text="Search Results"
                )
                return

    # === Fallback: AI Search ===
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
            price_text = f"BDT {p.get('price')}" if p.get("price") else "Price on request"
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


async def handle_recommend_for_you(ctx: BotContext, to: str):
    """Sends personalized recommendations to the user based on their past orders."""
    orders = await ctx.db.get_cached_orders(to)
    if not orders:
        await ctx.wa.send_text_message(to, "I don't have enough purchase history to make personalized recommendations yet. 😅 But here are some of our most popular items!")
        await handle_ai_search(ctx, to, "Please show me your most popular products and top categories.")
        return

    history_desc = []
    for o in orders[:5]:
        for item in o.get("items", []):
            history_desc.append(item.get("name"))
            
    if not history_desc:
        await ctx.wa.send_text_message(to, "I couldn't find items in your past orders. Here are some popular products!")
        await handle_ai_search(ctx, to, "Please show me your most popular products.")
        return

    purchased = ", ".join(set(history_desc))
    await ctx.wa.send_text_message(to, f"Based on your past purchases of:\n_{purchased}_\n\nLet me find some great recommendations for you... 🔍")
    
    prompt = f"I previously bought {purchased}. What other products from your store would you recommend for me?"
    
    history = await ctx.db.get_user_history(to)
    result = await ctx.agent.answer_query(prompt, history=history, orders=orders)
    products = result.get("products", [])
    
    if products:
        from media_utils import generate_collage
        image_urls = []
        for p in products[:4]:
            if p.get("images") and len(p["images"]) > 0:
                image_urls.append(p["images"][0].get("src"))
                
        collage_path = await generate_collage(image_urls, f"collage_{to}.jpg")
        
        caption = result.get("text", "Here are some recommendations for you!") + "\n\n"
        for p in products[:4]:
            price = f"BDT {p.get('price')}" if p.get('price') else ""
            caption += f"• {p['name']} ({price})\n"
            
        if collage_path:
            media_id = await ctx.wa.upload_media(collage_path)
            if media_id:
                await ctx.wa.send_image_message(to, media_id=media_id, caption=caption)
            else:
                await ctx.wa.send_text_message(to, caption)
            import os
            try:
                os.remove(collage_path)
            except:
                pass
        else:
            await ctx.wa.send_text_message(to, caption)
            
        rows = []
        for p in products[:4]:
            price_text = f"BDT {p.get('price')}" if p.get("price") else "Price on request"
            rows.append({
                "id": f"prod_{p['id']}",
                "title": p["name"][:24],
                "description": f"{price_text} - View details"[:72]
            })
        sections = [{"title": "Recommended Items", "rows": rows}]
        await ctx.wa.send_list_message(
            to=to,
            button_text="View Products",
            body_text="Click below to see more details or add to cart:",
            sections=sections,
            header_text="Your Recommendations"
        )
    else:
        await ctx.wa.send_text_message(to, result.get("text", "I couldn't find any specific recommendations right now."))

async def handle_change_language(ctx: BotContext, to: str):
    """Toggles language between en and bn."""
    lang = await ctx.db.get_user_language(to)
    new_lang = "bn" if lang == "en" else "en"
    await ctx.db.set_user_language(to, new_lang)
    await handle_main_menu(ctx, to)

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


async def _handle_wit_resume_bot(ctx: BotContext, to: str):
    """Resume bot for user after human agent handoff."""
    await ctx.db.set_bot_paused(to, False)
    await ctx.db.set_user_state(to, "idle")
    await ctx.wa.send_text_message(to, "✅ Bot resumed. How can I help you?")


# Map Wit.ai intent names → async handlers (used inside route_text)
# Defined at module level so it's built once at import time
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

        # Mark pending message as completed
        if pending_id:
            asyncio.create_task(ctx.db.mark_pending_completed(pending_id))

    except Exception as e:
        logger.error(f"Error handling WhatsApp message: {e}", exc_info=True)
        # Mark pending message as failed
        if pending_id:
            asyncio.create_task(ctx.db.mark_pending_completed(pending_id, error=str(e)[:500]))
        try:
            await ctx.wa.send_text_message(from_number, "Sorry, I had trouble processing that action. Returning to main menu.")
            await handle_main_menu(ctx, from_number)
        except Exception as send_err:
            logger.error(f"Failed to send error message to {from_number}: {send_err}")
