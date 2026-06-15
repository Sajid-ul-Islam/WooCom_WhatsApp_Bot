import os
import logging
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, PlainTextResponse
from dotenv import load_dotenv

from woocommerce_client import WooCommerceClient
from db import DatabaseClient
from whatsapp_client import WhatsAppClient
from rag_agent import RAGAgent

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("whatsapp_bot")

load_dotenv()

# Instantiate clients
wc = WooCommerceClient()
db = DatabaseClient()
wa = WhatsAppClient()
agent = RAGAgent()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events to verify configuration and warm up clients."""
    logger.info("WhatsApp WooCommerce Bot is starting up...")
    verify_token = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN")
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN")
    
    if not verify_token or not phone_id or not access_token:
        logger.error("WhatsApp credentials missing in environment variables. Webhook might fail.")
    else:
        logger.info(f"WhatsApp Client configured for Phone ID: {phone_id}")
        
    if not db.client:
        logger.error("Supabase client not initialized. Database and carts will not function.")
        
    yield
    logger.info("WhatsApp WooCommerce Bot is shutting down...")

app = FastAPI(lifespan=lifespan)

# --- Routing Logic for Chatbot ---

async def handle_main_menu(to: str):
    """Sends the main menu options using reply buttons."""
    text = (
        "Assalamu Alaikum! 👋\n\n"
        "Welcome to our WooCommerce Store! How can I help you today?\n\n"
        "Please select an option below, ask me a question about our products, "
        "or search for items directly."
    )
    buttons = [
        {"id": "menu_categories", "title": "Browse Categories"},
        {"id": "menu_cart", "title": "View Cart"},
        {"id": "menu_orders", "title": "My Orders"}
    ]
    await wa.send_reply_buttons(to, text, buttons)

async def handle_categories(to: str):
    """Sends product categories to the user as a List Message."""
    categories = await wc.get_categories()
    if not categories:
        await wa.send_text_message(to, "Sorry, I couldn't load store categories right now.")
        return

    # Prepare rows for list message (limit 10)
    rows = []
    for cat in categories[:10]:
        rows.append({
            "id": f"cat_{cat['id']}",
            "title": cat["name"],
            "description": f"View products in {cat['name']}"
        })
        
    sections = [{
        "title": "Store Categories",
        "rows": rows
    }]
    
    await wa.send_list_message(
        to=to,
        button_text="Select Category",
        body_text="Choose a category from the list below to view products:",
        sections=sections,
        header_text="Categories"
    )

async def handle_category_products(to: str, category_id: int):
    """Sends products in a specific category as a List Message."""
    products = await wc.get_products(category_id=category_id, per_page=10)
    if not products:
        await wa.send_text_message(to, "This category doesn't have any products currently.")
        return

    rows = []
    for p in products:
        price_text = f"${p.get('price')}" if p.get("price") else "Price on request"
        rows.append({
            "id": f"prod_{p['id']}",
            "title": p["name"],
            "description": f"{price_text} - View details"
        })
        
    sections = [{
        "title": "Available Products",
        "rows": rows
    }]
    
    await wa.send_list_message(
        to=to,
        button_text="Select Product",
        body_text=f"Here are the products in this category. Select one to see details:",
        sections=sections,
        header_text="Category Products"
    )

async def handle_product_detail(to: str, product_id: int):
    """Sends product details, including pricing, description, and image."""
    product = await wc.get_product(product_id)
    if not product:
        await wa.send_text_message(to, "Sorry, I couldn't find details for that product.")
        return
        
    name = product.get("name")
    price = f"${product.get('price')}" if product.get('price') else "Price on request"
    permalink = product.get("permalink", "")
    
    # Strip HTML from description
    import re
    desc_raw = product.get("description") or product.get("short_description") or "No description available."
    description = re.sub('<[^<]+?>', '', desc_raw).strip()
    # Truncate description if too long
    if len(description) > 300:
        description = description[:297] + "..."
        
    caption = (
        f"*{name}*\n"
        f"Price: *{price}*\n\n"
        f"{description}\n\n"
        f"Link: {permalink}"
    )

    # Get image
    images = product.get("images", [])
    image_url = images[0].get("src") if images else None
    
    buttons = [
        {"id": f"add_{product_id}", "title": "🛒 Add to Cart"},
        {"id": "menu_cart", "title": "🛍️ View Cart"},
        {"id": "menu_main", "title": "🏠 Main Menu"}
    ]
    
    if image_url:
        # Send image with buttons by sending image card, followed by the buttons message
        await wa.send_image_message(to, image_url, caption=caption)
        await wa.send_reply_buttons(to, "What would you like to do next?", buttons)
    else:
        await wa.send_reply_buttons(to, caption, buttons)

async def handle_add_to_cart(to: str, product_id: int, quantity: int = 1):
    """Adds a product to the user's Supabase cart and notifies them."""
    product = await wc.get_product(product_id)
    if not product:
        await wa.send_text_message(to, "Sorry, that product is no longer available.")
        return
        
    images = product.get("images", [])
    image_url = images[0].get("src") if images else ""
    
    cart = await db.add_to_cart(
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
    await wa.send_reply_buttons(to, text, buttons)

async def handle_view_cart(to: str):
    """Displays the user's current shopping cart and actions."""
    cart_items = await db.get_cart(to)
    if not cart_items:
        text = "Your shopping cart is currently empty! 🛒\n\nBrowse our catalog to add items."
        buttons = [
            {"id": "menu_categories", "title": "Browse Catalog"},
            {"id": "menu_main", "title": "🏠 Main Menu"}
        ]
        await wa.send_reply_buttons(to, text, buttons)
        return
        
    cart_text = "🛍️ *Your Shopping Cart:*\n\n"
    total = 0.0
    for item in cart_items:
        subtotal = item["price"] * item["quantity"]
        total += subtotal
        cart_text += f"• *{item['name']}* x{item['quantity']}\n  Price: ${item['price']:.2f} (Subtotal: ${subtotal:.2f})\n  Remove: Reply _Remove {item['product_id']}_\n\n"
        
    cart_text += f"*Total Amount: ${total:.2f}*"
    
    buttons = [
        {"id": "cart_checkout", "title": "💳 Checkout"},
        {"id": "cart_clear", "title": "🗑️ Clear Cart"},
        {"id": "menu_main", "title": "🏠 Main Menu"}
    ]
    await wa.send_reply_buttons(to, cart_text, buttons)

async def handle_checkout_prompt(to: str):
    """Instructs the user on how to complete their checkout."""
    cart_items = await db.get_cart(to)
    if not cart_items:
        await wa.send_text_message(to, "Your cart is empty. Please add items before checking out.")
        return
        
    instruction = (
        "💳 *Checkout Instructions*\n\n"
        "To place your cash-on-delivery order, please reply in the following format:\n\n"
        "*Checkout: [Your Full Name], [Your Shipping Address]*\n\n"
        "Example:\n"
        "_Checkout: John Doe, 123 Main Street, New York_"
    )
    await wa.send_text_message(to, instruction)

async def handle_process_checkout(to: str, text: str):
    """Processes the order creation in WooCommerce and clears user cart."""
    # Pattern matching "Checkout: Name, Address"
    try:
        details = text.split(":", 1)[1].strip()
        parts = details.split(",", 1)
        if len(parts) < 2:
            raise ValueError()
        name = parts[0].strip()
        address = parts[1].strip()
    except Exception:
        await wa.send_text_message(
            to, 
            "⚠️ Invalid checkout format.\n\nPlease reply exactly like this:\n*Checkout: Name, Full Address*"
        )
        return
        
    cart_items = await db.get_cart(to)
    if not cart_items:
        await wa.send_text_message(to, "Your cart is empty. Browse products to start shopping!")
        return
        
    await wa.send_text_message(to, "⏳ Processing your order, please wait...")
    
    order = await wc.create_order(
        phone_number=to,
        customer_name=name,
        cart_items=cart_items,
        address_text=address
    )
    
    if not order:
        await wa.send_text_message(to, "❌ Failed to place order in our system. Please try again later.")
        return
        
    # Sync created order with DB order cache
    await db.cache_orders([order], to)
    # Clear cart
    await db.clear_cart(to)
    
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
    await wa.send_reply_buttons(to, success_text, buttons)

async def handle_view_orders(to: str):
    """Displays order history and status cached locally."""
    # First attempt to fetch live from WooCommerce API, and update local cache
    live_orders = await wc.get_orders_by_phone(to)
    if live_orders:
        await db.cache_orders(live_orders, to)
        
    orders = await db.get_cached_orders(to)
    if not orders:
        text = "You haven't placed any orders with this phone number yet."
        buttons = [
            {"id": "menu_categories", "title": "Start Shopping"},
            {"id": "menu_main", "title": "🏠 Main Menu"}
        ]
        await wa.send_reply_buttons(to, text, buttons)
        return
        
    order_text = "📦 *Your Recent Orders:*\n\n"
    for o in orders[:5]:  # Display recent 5 orders
        items_desc = ", ".join([f"{item['name']} (x{item['quantity']})" for item in o.get("items", [])])
        # Format dates nicely
        date_str = o.get("created_at")[:10] if o.get("created_at") else "N/A"
        order_text += (
            f"• *Order #{o['id']}* - {date_str}\n"
            f"  Status: *{o['status'].upper()}*\n"
            f"  Items: {items_desc}\n"
            f"  Total: ${o['total']:.2f}\n\n"
        )
        
    buttons = [
        {"id": "menu_main", "title": "🏠 Main Menu"}
    ]
    await wa.send_reply_buttons(to, order_text, buttons)

async def handle_clear_cart(to: str):
    """Clears the shopping cart."""
    await db.clear_cart(to)
    buttons = [
        {"id": "menu_categories", "title": "Browse Catalog"},
        {"id": "menu_main", "title": "🏠 Main Menu"}
    ]
    await wa.send_reply_buttons(to, "🗑️ Your shopping cart has been cleared.", buttons)

async def handle_ai_search(to: str, query: str):
    """Passes user text query to the RAG Agent and returns LLM and matching products."""
    await wa.send_text_message(to, "🔍 Searching the catalog, please wait...")
    
    history = await db.get_user_history(to)
    
    result = await agent.answer_query(query, history=history)
    response_text = result["text"]
    matching_products = result["products"]
    
    history.append({"role": "user", "content": query})
    history.append({"role": "assistant", "content": response_text})
    history = history[-10:] # keep last 10 messages
    await db.update_user_history(to, history)
    
    # Send the LLM-generated reply
    await wa.send_text_message(to, response_text)
    
    # If products match, offer them in a quick list menu for direct selection
    if matching_products:
        rows = []
        for p in matching_products:
            price_text = f"${p.get('price')}" if p.get('price') else "Price on request"
            rows.append({
                "id": f"prod_{p['id']}",
                "title": p["name"],
                "description": f"{price_text} - View details"
            })
        sections = [{
            "title": "Recommended Items",
            "rows": rows
        }]
        await wa.send_list_message(
            to=to,
            button_text="View Match",
            body_text="Click below to see the specifications, photos or add recommended products to cart:",
            sections=sections,
            header_text="Matching Results"
        )
    else:
        # Give fallback buttons to main menu
        buttons = [
            {"id": "menu_categories", "title": "Browse Categories"},
            {"id": "menu_main", "title": "🏠 Main Menu"}
        ]
        await wa.send_reply_buttons(to, "What would you like to do?", buttons)

# --- Webhook Endpoint Handlers ---

@app.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(request: Request):
    """Meta webhook verification endpoint."""
    verify_token = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN")
    
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    
    if mode and token:
        if mode == "subscribe" and token == verify_token:
            logger.info("Webhook verified successfully by Meta.")
            return challenge
        else:
            logger.warning(f"Verification token mismatch: received '{token}', expected '{verify_token}'")
            raise HTTPException(status_code=403, detail="Verification token mismatch")
            
    raise HTTPException(status_code=400, detail="Missing verification parameters")

@app.post("/webhook")
async def whatsapp_webhook(request: Request):
    """Meta webhook POST receiver endpoint."""
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse incoming JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Log incoming webhook JSON for debugging
    logger.debug(f"Webhook received: {json.dumps(body)}")

    # Check for statuses update (sent, delivered, read) to ignore
    entry = body.get("entry", [{}])[0]
    changes = entry.get("changes", [{}])[0]
    value = changes.get("value", {})
    
    if "messages" not in value:
        # Status update or metadata update, return 200 OK
        return JSONResponse({"status": "ignored"})
        
    message = value["messages"][0]
    from_number = message["from"]
    
    msg_type = message.get("type")
    
    # Initialize variables for action routing
    action_id = ""
    incoming_text = ""
    
    # 1. Parse message type
    if msg_type == "interactive":
        interactive = message.get("interactive", {})
        int_type = interactive.get("type")
        
        if int_type == "button_reply":
            action_id = interactive.get("button_reply", {}).get("id", "")
        elif int_type == "list_reply":
            action_id = interactive.get("list_reply", {}).get("id", "")
            
    elif msg_type == "text":
        incoming_text = message.get("text", {}).get("body", "").strip()

    # 2. Route payload
    try:
        # HUMAN HANDOFF CHECK
        await db.upsert_user(from_number)
        
        if incoming_text:
            text_lower = incoming_text.lower()
            if text_lower in ["/resume", "resume", "resume bot"]:
                await db.set_bot_paused(from_number, False)
                await wa.send_text_message(from_number, "✅ Bot resumed. How can I help you?")
                return JSONResponse({"status": "ok"})
                
        is_paused = await db.is_bot_paused(from_number)
        if is_paused:
            logger.info(f"Bot paused for {from_number}. Ignoring message.")
            return JSONResponse({"status": "ignored"})
            
        if action_id:
            logger.info(f"Processing action '{action_id}' from {from_number}")
            
            # Category navigation
            if action_id.startswith("cat_"):
                cat_id = int(action_id.split("_")[1])
                await handle_category_products(from_number, cat_id)
                
            # Product details view
            elif action_id.startswith("prod_"):
                prod_id = int(action_id.split("_")[1])
                await handle_product_detail(from_number, prod_id)
                
            # Add product to cart
            elif action_id.startswith("add_"):
                prod_id = int(action_id.split("_")[1])
                await handle_add_to_cart(from_number, prod_id)
                
            # Menu buttons routing
            elif action_id == "menu_main":
                await handle_main_menu(from_number)
            elif action_id == "menu_categories":
                await handle_categories(from_number)
            elif action_id == "menu_cart":
                await handle_view_cart(from_number)
            elif action_id == "menu_orders":
                await handle_view_orders(from_number)
            elif action_id == "cart_checkout":
                await handle_checkout_prompt(from_number)
            elif action_id == "cart_clear":
                await handle_clear_cart(from_number)
            else:
                await wa.send_text_message(from_number, "I didn't recognize that action. Returning to main menu.")
                await handle_main_menu(from_number)
                
        elif incoming_text:
            logger.info(f"Processing text message '{incoming_text}' from {from_number}")
            text_lower = incoming_text.lower()
            
            # Start/Hello
            if text_lower in ["/start", "hi", "hello", "menu", "hey", "assalamu alaikum", "start"]:
                await handle_main_menu(from_number)
                
            # Category browser keyword
            elif text_lower in ["categories", "browse", "catalog"]:
                await handle_categories(from_number)
                
            # Cart browser keyword
            elif text_lower in ["cart", "shopping cart", "view cart"]:
                await handle_view_cart(from_number)
                
            # Order history keyword
            elif text_lower in ["orders", "my order", "my orders", "status"]:
                await handle_view_orders(from_number)
                
            # Add command by typing (fallback for manual add, e.g. "Add 123")
            elif text_lower.startswith("add ") or text_lower.startswith("add"):
                # extract ID
                try:
                    parts = text_lower.split()
                    prod_id = int("".join(filter(str.isdigit, parts[-1])))
                    await handle_add_to_cart(from_number, prod_id)
                except Exception:
                    await wa.send_text_message(from_number, "To add a product, please type *Add [Product ID]* (e.g. *Add 105*).")
                    
            # Remove command by typing (e.g. "Remove 123")
            elif text_lower.startswith("remove ") or text_lower.startswith("remove"):
                try:
                    parts = text_lower.split()
                    prod_id = int("".join(filter(str.isdigit, parts[-1])))
                    await db.remove_from_cart(from_number, prod_id)
                    await wa.send_text_message(from_number, f"❌ Removed product from cart.")
                    await handle_view_cart(from_number)
                except Exception:
                    await wa.send_text_message(from_number, "To remove an item, type *Remove [Product ID]* (e.g. *Remove 105*).")
                    
            # Pause bot
            elif text_lower in ["/talktohuman", "talk to human", "human", "support"]:
                await db.set_bot_paused(from_number, True)
                await wa.send_text_message(from_number, "⏸️ I have paused my automated responses. A human agent will be with you shortly. Type */resume* when you want me to take over again.")
                
            # Process checkout command
            elif text_lower.startswith("checkout:") or text_lower.startswith("checkout"):
                await handle_process_checkout(from_number, incoming_text)
                
            # Treat everything else as AI search/QA query
            else:
                await handle_ai_search(from_number, incoming_text)
                
    except Exception as e:
        logger.error(f"Error handling WhatsApp message: {e}", exc_info=True)
        # Try to send a simple error fallback message to user
        try:
            await wa.send_text_message(from_number, "Sorry, I had trouble processing that action. Returning to main menu.")
            await handle_main_menu(from_number)
        except Exception:
            pass

    return JSONResponse({"status": "ok"})

@app.post("/woo-webhook")
async def woo_webhook(request: Request):
    """Webhook to receive order updates from WooCommerce and notify users via WhatsApp."""
    try:
        body = await request.json()
        logger.info(f"WooCommerce webhook received: {body.get('id')}")
        
        status = body.get("status")
        billing = body.get("billing", {})
        phone = billing.get("phone")
        order_id = body.get("id")
        
        if phone and status and order_id:
            message = f"🔔 *Order Update*\n\nYour order #{order_id} is now: *{status.upper()}*."
            await wa.send_text_message(phone, message)
            
        return JSONResponse({"status": "ok"})
    except Exception as e:
        logger.error(f"Error processing woo webhook: {e}")
        return JSONResponse({"status": "error"})
