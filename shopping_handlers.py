import os
import re
import logging
from context import BotContext
from utils import clean_html
from i18n import get_text, format_text

logger = logging.getLogger(__name__)


async def handle_main_menu(ctx: BotContext, to: str):
    """Sends a clean, hierarchical main menu with clear sections."""
    # Fetch dynamic user state (cart items)
    cart = await ctx.db.get_cart(to)
    cart_items = sum(item.get("quantity", 1) for item in cart)
    lang = await ctx.db.get_user_language(to)

    text = get_text(lang, "welcome")

    # 1. Shopping (Primary actions)
    shopping_rows = [
        {"id": "menu_search", "title": get_text(lang, "menu_search"), "description": get_text(lang, "desc_search")},
        {"id": "menu_categories", "title": get_text(lang, "menu_categories"), "description": get_text(lang, "desc_explore")},
        {"id": "menu_recommend", "title": get_text(lang, "menu_recommend"), "description": get_text(lang, "desc_for_you")},
        {"id": "menu_size", "title": get_text(lang, "menu_size"), "description": get_text(lang, "desc_find_size")}
    ]

    # 2. Cart & Orders (Transactional)
    transactional_rows = [
        {"id": "menu_cart", "title": get_text(lang, "menu_cart"), "description": get_text(lang, "desc_cart_items") if cart_items > 0 else get_text(lang, "desc_empty_cart")},
        {"id": "menu_orders", "title": get_text(lang, "menu_orders"), "description": get_text(lang, "desc_view_orders")}
    ]

    # Update cart title with count
    if cart_items > 0:
        transactional_rows[0]["title"] = f"({cart_items}) {get_text(lang, 'menu_cart')}"

    # 3. Help & Settings (Secondary)
    settings_rows = [
        {"id": "menu_human", "title": get_text(lang, "menu_human"), "description": get_text(lang, "desc_talk_human")},
        {"id": "menu_language", "title": get_text(lang, "menu_language"), "description": get_text(lang, "desc_change_lang")},
        {"id": "menu_cancel_order", "title": get_text(lang, "menu_cancel_order"), "description": get_text(lang, "desc_cancel_order")}
    ]

    if cart_items > 0:
        settings_rows.append({
            "id": "cart_clear",
            "title": get_text(lang, "cart_clear"),
            "description": get_text(lang, "desc_clear_cart")
        })

    sections = [
        {"title": get_text(lang, "section_store"), "rows": shopping_rows},
        {"title": get_text(lang, "section_account"), "rows": transactional_rows},
        {"title": get_text(lang, "section_support"), "rows": settings_rows}
    ]

    await ctx.wa.send_list_message(
        to=to,
        button_text=get_text(lang, "btn_open_menu"),
        body_text=text,
        sections=sections,
        header_text="DEEN Commerce"
    )


async def handle_search_prompt(ctx: BotContext, to: str):
    """Prompts the user to type a search query for product lookup."""
    lang = await ctx.db.get_user_language(to)
    await ctx.db.set_user_state(to, "search_pending")
    await ctx.wa.send_text_message(
        to,
        get_text(lang, "search_prompt")
    )


async def handle_categories(ctx: BotContext, to: str):
    """Sends product categories to the user as a List Message, split into Promos, Men's, and Others."""
    # Fetch top-level categories (for promos and others) and MEN's subcategories (for regular items)
    top_categories = await ctx.wc.get_categories(parent=0)

    # Men's category parent ID — configurable via env var; set to 0 to skip the men's section
    men_parent_id = int(os.getenv("MEN_CATEGORY_PARENT_ID", "0"))
    men_categories = await ctx.wc.get_categories(parent=men_parent_id) if men_parent_id > 0 else []
    
    lang = await ctx.db.get_user_language(to)
    if not top_categories and not men_categories:
        await ctx.wa.send_text_message(to, get_text(lang, "no_categories"))
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
                "description": f"{get_text(lang, 'btn_view_detail')} in {cat['name']}"[:72]
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
        sections.append({"title": get_text(lang, "section_special_offers"), "rows": final_promo})
    if final_mens:
        sections.append({"title": get_text(lang, "section_mens_collection"), "rows": final_mens})
    if final_other:
        sections.append({"title": get_text(lang, "section_other_categories"), "rows": final_other})
    
    await ctx.wa.send_list_message(
        to=to,
        button_text=get_text(lang, "categories_btn"),
        body_text=get_text(lang, "categories_body"),
        sections=sections,
        header_text="Categories"
    )


async def handle_category_products(ctx: BotContext, to: str, category_id: int):
    """Sends products in a specific category as a List Message."""
    lang = await ctx.db.get_user_language(to)
    products = await ctx.wc.get_products(category_id=category_id, per_page=10)
    if not products:
        await ctx.wa.send_text_message(to, get_text(lang, "no_products_in_cat"))
        return

    rows = []
    for p in products:
        price_text = f"BDT {p.get('price')}" if p.get("price") else get_text(lang, "price_on_request")
        name = p["name"]
        truncated_name = name[:22] + "..." if len(name) > 24 else name
        rows.append({
            "id": f"prod_{p['id']}",
            "title": truncated_name,
            "description": f"{price_text} - {get_text(lang, 'desc_view_detail')}"
        })

    sections = [{"title": get_text(lang, "section_available_products"), "rows": rows}]

    await ctx.wa.send_list_message(
        to=to,
        button_text=get_text(lang, "btn_select_product"),
        body_text=get_text(lang, "select_product"),
        sections=sections,
        header_text="Category Products"
    )


async def handle_product_detail(ctx: BotContext, to: str, product_id: int):
    """Sends product details dynamically, extracting precise pricing, stock, and metadata.
    Detects if product has variations (e.g. sizes) and adjusts buttons accordingly."""
    lang = await ctx.db.get_user_language(to)
    product = await ctx.wc.get_product(product_id)
    if not product:
        await ctx.wa.send_text_message(to, get_text(lang, "no_product_details"))
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
        price_display = get_text(lang, "price_on_request")

    # 2. Stock Status
    stock_status = product.get("stock_status", "instock")
    if stock_status == "instock":
        stock_display = get_text(lang, "in_stock")
        qty = product.get("stock_quantity")
        if qty:
            stock_display += f" ({qty} available)"
    elif stock_status == "outofstock":
        stock_display = get_text(lang, "out_of_stock")
    else:
        stock_display = get_text(lang, "on_backorder")
        
    # 3. Categories & Rating
    cats = product.get("categories", [])
    cat_names = ", ".join(c.get("name", "") for c in cats) if cats else get_text(lang, "general_category")
    
    rating = product.get("average_rating", "0.0")
    rating_display = f"⭐ {rating}/5.0" if float(rating) > 0 else get_text(lang, "no_reviews")

    # 4. Clean Description
    desc_raw = product.get("short_description") or product.get("description") or ""
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
            {"id": f"size_sel_{product_id}", "title": get_text(lang, "btn_select_size")},
            {"id": f"size_chart_{product_id}", "title": get_text(lang, "btn_size_chart")},
            {"id": "menu_main", "title": get_text(lang, "btn_main_menu")}
        ]
    else:
        buttons = [
            {"id": f"add_{product_id}", "title": get_text(lang, "btn_add_to_cart")},
            {"id": "menu_cart", "title": get_text(lang, "btn_view_cart")},
            {"id": "menu_main", "title": get_text(lang, "btn_main_menu")}
        ]

    if image_url:
        await ctx.wa.send_image_message(to, image_url, caption=caption)
        await ctx.wa.send_reply_buttons(to, get_text(lang, "what_next"), buttons)
    else:
        await ctx.wa.send_reply_buttons(to, caption, buttons)


async def handle_show_variations(ctx: BotContext, to: str, product_id: int):
    """Shows available size options for a variable product as a selectable list."""
    lang = await ctx.db.get_user_language(to)
    product = await ctx.wc.get_product(product_id)
    if not product:
        await ctx.wa.send_text_message(to, get_text(lang, "no_product_details"))
        return

    variations = await ctx.wc.get_product_variations(product_id)
    if not variations:
        await ctx.wa.send_text_message(to, get_text(lang, "no_sizes_available"))
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
            "description": f"{price_text}" if in_stock else f"{price_text} - {get_text(lang, 'desc_out_of_stock')}"
        })

    if not rows:
        await ctx.wa.send_text_message(to, get_text(lang, "no_sizes_available_now"))
        return

    sections = [
        {
            "title": get_text(lang, "available_sizes"),
            "rows": rows
        },
        {
            "title": get_text(lang, "help_section"),
            "rows": [
                {"id": f"size_chart_{product_id}", "title": get_text(lang, "view_size_chart"), "description": get_text(lang, "see_sizing_guide")}
            ]
        }
    ]

    await ctx.wa.send_list_message(
        to=to,
        button_text=get_text(lang, "btn_select_size"),
        body_text=format_text(lang, "choose_size_for", product_name=product.get('name', '')),
        sections=sections,
        header_text="Select Size"
    )


async def handle_size_chart(ctx: BotContext, to: str, product_id: int):
    """Shows the sizing guide/chart by extracting an image from the product description."""
    lang = await ctx.db.get_user_language(to)
    product = await ctx.wc.get_product(product_id)
    image_url = None

    if product:
        # Search for an image in the description or short description
        html_content = product.get("description", "") + " " + product.get("short_description", "")
        match = re.search(r'<img\s+[^>]*src=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
        if match:
            image_url = match.group(1)

    buttons = [
        {"id": f"size_sel_{product_id}", "title": get_text(lang, "btn_select_size")},
        {"id": "menu_main", "title": get_text(lang, "btn_main_menu")}
    ]

    if image_url:
        await ctx.wa.send_image_message(to, image_url, caption=get_text(lang, "size_guide_title"))
        await ctx.wa.send_reply_buttons(to, get_text(lang, "what_next"), buttons)
    else:
        # Fallback to default size guide if no image is found
        await ctx.wa.send_reply_buttons(to, get_text(lang, "size_guide_full"), buttons)


async def handle_ai_search(ctx: BotContext, to: str, query: str):
    """Passes user text query to the RAG Agent and returns LLM and matching products.
    Uses a fast-path fuzzy match to bypass LLM for exact or very close matches."""
    from support_handlers import handle_human_agent
    
    # === Fast Path: Direct Fuzzy Match ===
    lang = await ctx.db.get_user_language(to)
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
                    price_text = f"BDT {p.get('price')}" if p.get("price") else get_text(lang, "price_on_request")
                    name = p.get("name", "")
                    truncated_name = name[:22] + "..." if len(name) > 24 else name
                    rows.append({
                        "id": f"prod_{p['id']}",
                        "title": truncated_name,
                        "description": f"{price_text} - {get_text(lang, 'desc_view_detail')}"[:72]
                    })
                sections = [{"title": get_text(lang, "section_available_products"), "rows": rows}]
                await ctx.wa.send_list_message(
                    to=to,
                    button_text=get_text(lang, "btn_view_matches"),
                    body_text=get_text(lang, "found_matches"),
                    sections=sections,
                    header_text="Search Results"
                )
                return

    # === Fallback: AI Search ===
    await ctx.wa.send_text_message(to, get_text(lang, "search_wait"))

    history = await ctx.db.get_user_history(to)
    orders = await ctx.db.get_cached_orders(to)

    result = await ctx.agent.answer_query(query, history=history, orders=orders)
    sentiment = result.get("sentiment", "neutral")

    # Sentiment auto-escalation
    if sentiment in ["frustrated", "angry"]:
        logger.info(f"Auto-escalating user {to} due to {sentiment} sentiment.")
        await ctx.wa.send_text_message(to, get_text(lang, "escalation_msg"))
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
            price_text = f"BDT {p.get('price')}" if p.get("price") else get_text(lang, "price_on_request")
            name = p["name"]
            truncated_name = name[:22] + "..." if len(name) > 24 else name
            rows.append({
                "id": f"prod_{p['id']}",
                "title": truncated_name,
                "description": f"{price_text} - {get_text(lang, 'desc_view_detail')}"
            })
        sections = [{"title": get_text(lang, "recommended_items_title"), "rows": rows}]
        await ctx.wa.send_list_message(
            to=to,
            button_text=get_text(lang, "btn_view_matches"),
            body_text=get_text(lang, "click_to_view"),
            sections=sections,
            header_text=get_text(lang, "matching_results_title")
        )
    else:
        buttons = [
            {"id": "menu_categories", "title": get_text(lang, "menu_categories")},
            {"id": "menu_main", "title": get_text(lang, "btn_main_menu")}
        ]
        await ctx.wa.send_reply_buttons(to, get_text(lang, "browse_prompt"), buttons)


async def handle_sku_search(ctx: BotContext, to: str, sku: str):
    """Looks up a product by SKU code and displays its details if found.

    If no product matches the SKU, falls through to AI search so the
    text is still processed as a normal query (handles false positives
    gracefully).
    """
    product = await ctx.wc.get_product_by_sku(sku)
    if not product:
        # Not a valid SKU — fall through to normal text search
        await handle_ai_search(ctx, to, sku)
        return

    # Found the product — reuse the existing product detail display
    await handle_product_detail(ctx, to, product["id"])


async def handle_recommend_for_you(ctx: BotContext, to: str):
    """Sends personalized recommendations to the user based on their past orders."""
    lang = await ctx.db.get_user_language(to)
    orders = await ctx.db.get_cached_orders(to)
    if not orders:
        await ctx.wa.send_text_message(to, get_text(lang, "recommend_no_history"))
        await handle_ai_search(ctx, to, "Please show me your most popular products and top categories.")
        return

    history_desc = []
    for o in orders[:5]:
        for item in o.get("items", []):
            history_desc.append(item.get("name"))
            
    if not history_desc:
        await ctx.wa.send_text_message(to, get_text(lang, "recommend_no_items"))
        await handle_ai_search(ctx, to, "Please show me your most popular products.")
        return

    purchased = ", ".join(set(history_desc))
    await ctx.wa.send_text_message(to, format_text(lang, "recommend_searching", purchased=purchased))
    
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
        
        caption = result.get("text", get_text(lang, "recommended_items_title")) + "\n\n"
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
            price_text = f"BDT {p.get('price')}" if p.get("price") else get_text(lang, "price_on_request")
            name = p["name"]
            truncated_name = name[:22] + "..." if len(name) > 24 else name
            rows.append({
                "id": f"prod_{p['id']}",
                "title": truncated_name,
                "description": f"{price_text} - {get_text(lang, 'desc_view_detail')}"[:72]
            })
        sections = [{"title": get_text(lang, "recommended_items_title"), "rows": rows}]
        await ctx.wa.send_list_message(
            to=to,
            button_text=get_text(lang, "btn_view_products"),
            body_text=get_text(lang, "click_to_view"),
            sections=sections,
            header_text="Your Recommendations"
        )
    else:
        await ctx.wa.send_text_message(to, result.get("text", get_text(lang, "no_recommendations")))
