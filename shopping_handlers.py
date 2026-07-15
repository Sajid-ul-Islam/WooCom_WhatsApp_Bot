import os
import re
import logging
from context import BotContext
from utils import clean_html
from i18n import get_text

logger = logging.getLogger(__name__)


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


async def handle_ai_search(ctx: BotContext, to: str, query: str):
    """Passes user text query to the RAG Agent and returns LLM and matching products.
    Uses a fast-path fuzzy match to bypass LLM for exact or very close matches."""
    from support_handlers import handle_human_agent
    
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
