import os
import re
import time
import logging
import json
import asyncio
from pydantic import BaseModel
from collections import defaultdict
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse, PlainTextResponse, HTMLResponse
from dotenv import load_dotenv

from woocommerce_client import WooCommerceClient
from db import DatabaseClient, normalize_phone
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

# --- Simple In-Memory Rate Limiter ---

RATE_LIMIT_WINDOW = 10  # seconds
RATE_LIMIT_MAX = 5      # max messages per window

_rate_buckets: dict[str, list[float]] = defaultdict(list)

def _is_rate_limited(phone: str) -> bool:
    """Return True if the phone number has exceeded the rate limit."""
    now = time.monotonic()
    bucket = _rate_buckets[phone]
    # Prune old timestamps
    _rate_buckets[phone] = [t for t in bucket if now - t < RATE_LIMIT_WINDOW]
    bucket = _rate_buckets[phone]
    if len(bucket) >= RATE_LIMIT_MAX:
        return True
    bucket.append(now)
    return False

# --- Simple In-Memory Message Deduplication ---
# Maps message_id -> timestamp (when it was received)
_processed_message_ids: dict[str, float] = {}
DEDUPLICATION_WINDOW = 300  # 5 minutes in seconds

def _is_duplicate_message(msg_id: str) -> bool:
    """Check if the message has already been processed or is currently processing."""
    if not msg_id:
        return False
    now = time.monotonic()
    
    # Prune old message IDs to prevent memory growth
    expired_ids = [k for k, t in _processed_message_ids.items() if now - t > DEDUPLICATION_WINDOW]
    for k in expired_ids:
        _processed_message_ids.pop(k, None)
        
    if msg_id in _processed_message_ids:
        return True
        
    _processed_message_ids[msg_id] = now
    return False

# --- Max incoming message length ---
MAX_INCOMING_TEXT_LEN = 1000


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events: load secrets from Supabase, verify config, warm up clients."""
    global wc, wa, agent  # noqa: PLW0603 – re-init after config load
    
    logger.info("WhatsApp WooCommerce Bot is starting up...")
    
    # --- Load secrets from Supabase config table ---
    try:
        remote_config = await db.get_app_config()
        if remote_config:
            loaded_keys = []
            for key, value in remote_config.items():
                if value and not os.getenv(key):
                    # Only set if not already overridden by a local env var
                    os.environ[key] = value
                    loaded_keys.append(key)
            if loaded_keys:
                logger.info(f"Loaded {len(loaded_keys)} config keys from Supabase: {', '.join(loaded_keys)}")
            else:
                logger.info("All config keys already set locally; Supabase config skipped.")
        else:
            logger.warning("No config rows found in Supabase 'config' table (or table doesn't exist).")
    except Exception as e:
        logger.warning(f"Could not load remote config from Supabase: {e}. Falling back to env vars.")
    
    # Re-initialize ALL clients so they pick up the freshly-loaded keys
    wc = WooCommerceClient()
    wa = WhatsAppClient()
    agent = RAGAgent()
    
    # --- Verify config ---
    verify_token = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN")
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN")
    
    if not verify_token or not phone_id or not access_token:
        logger.error("WhatsApp credentials missing. Check Supabase 'config' table or env vars.")
    else:
        logger.info(f"WhatsApp Client configured for Phone ID: {phone_id}")
    
    wc_url = os.getenv("WOOCOMMERCE_URL", "not set")
    logger.info(f"WooCommerce URL: {wc_url}")
    
    llm_provider = os.getenv("LLM_PROVIDER", "not set")
    logger.info(f"LLM Provider: {llm_provider}")
    
    if not db.client:
        logger.error("Supabase client not initialized. Database and carts will not function.")
        
    # --- Start Abandoned Cart Worker ---
    async def abandoned_cart_worker():
        while True:
            try:
                # Run every 1 hour (3600 seconds)
                await asyncio.sleep(3600)
                abandoned = await db.get_abandoned_carts(hours=24)
                for cart in abandoned:
                    phone = cart.get("phone_number")
                    if phone:
                        msg = (
                            "🛒 *Friendly Reminder!*\n\n"
                            "You left some items in your shopping cart. "
                            "Would you like to complete your order?\n\n"
                            "Reply with *Cart* to view your items, or browse more to add others!"
                        )
                        await wa.send_text_message(phone, msg)
                        await asyncio.sleep(1) # Prevent rate limiting
            except Exception as e:
                logger.error(f"Abandoned cart worker error: {e}")

    # Fire and forget the background task
    asyncio.create_task(abandoned_cart_worker())
    
    yield
    logger.info("WhatsApp WooCommerce Bot is shutting down...")

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def health_check():
    """Root health check — confirms the app is running."""
    return {"status": "ok", "service": "WooCom WhatsApp Bot"}

@app.get("/api/dashboard-stats")
async def api_dashboard_stats():
    """Returns real-time dashboard statistics from Supabase."""
    stats = await db.get_dashboard_stats()
    return JSONResponse(content=stats)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Serves the dashboard HTML interface."""
    try:
        with open("public/dashboard.html", "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Dashboard UI not found. Please create public/dashboard.html</h1>", status_code=404)

class BroadcastRequest(BaseModel):
    message: str

@app.post("/api/broadcast")
async def broadcast_message(req: BroadcastRequest):
    """Sends a promotional message to all active users."""
    users = await db.get_all_active_users()
    if not users:
        return JSONResponse({"status": "error", "message": "No users found."})
        
    # Safety cap: limit to 50 for testing/preventing bans
    users = users[:50]
    
    count = 0
    for phone in users:
        try:
            await wa.send_text_message(phone, req.message)
            count += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Broadcast failed for {phone}: {e}")
            
    return JSONResponse({"status": "ok", "message": f"Broadcast sent to {count} users."})

# --- Routing Logic for Chatbot ---

async def handle_main_menu(to: str):
    """Sends the main menu options using a List Message (supports up to 10 options)."""
    text = (
        "Assalamu Alaikum! 👋\n\n"
        "Welcome to our WooCommerce Store! How can I help you today?\n\n"
        "Please select an option from the menu below, ask me a question about our products, "
        "or search for items directly."
    )
    
    # Using a list message because WhatsApp limits normal buttons to exactly 3!
    sections = [{
        "title": "Main Menu Options",
        "rows": [
            {"id": "menu_categories", "title": "🛍️ Browse Categories", "description": "Explore our store's catalog"},
            {"id": "menu_cart", "title": "🛒 View Cart", "description": "Check your selected items"},
            {"id": "menu_orders", "title": "📦 My Orders", "description": "Track your past purchases"},
            {"id": "cart_clear", "title": "🗑️ Clear Cart", "description": "Empty your shopping cart"},
            {"id": "menu_human", "title": "🧑‍💻 Talk to Human", "description": "Pause the AI and talk to staff"}
        ]
    }]
    
    await wa.send_list_message(
        to=to,
        button_text="Tap for Options",
        body_text=text,
        sections=sections,
        header_text="Main Menu"
    )

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

async def handle_remove_from_cart(to: str, product_id: int):
    """Removes a product from the user's cart and shows updated cart."""
    await db.remove_from_cart(to, product_id)
    await wa.send_text_message(to, f"❌ Removed product #{product_id} from your cart.")
    await handle_view_cart(to)

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
    """Instructs the user on how to complete their checkout and sets state."""
    cart_items = await db.get_cart(to)
    if not cart_items:
        await wa.send_text_message(to, "Your cart is empty. Please add items before checking out.")
        return
    
    # Transition user into checkout_pending state
    await db.set_user_state(to, "checkout_pending")
    
    instruction = (
        "💳 *Checkout Instructions*\n\n"
        "Please reply with your name and shipping address in the following format:\n\n"
        "*Your Full Name, Your Shipping Address*\n\n"
        "Example:\n"
        "_John Doe, 123 Main Street, New York_\n\n"
        "Or type *cancel* to go back."
    )
    await wa.send_text_message(to, instruction)

async def handle_process_checkout(to: str, text: str):
    """Processes the order creation in WooCommerce and clears user cart."""
    # Parse: "Name, Address" (no prefix needed when coming from state machine)
    try:
        parts = text.split(",", 1)
        if len(parts) < 2:
            raise ValueError()
        name = parts[0].strip()
        address = parts[1].strip()
        if not name or not address:
            raise ValueError()
    except Exception:
        await wa.send_text_message(
            to, 
            "⚠️ Invalid format.\n\nPlease reply like this:\n*Name, Full Address*\n\nOr type *cancel* to go back."
        )
        return
        
    cart_items = await db.get_cart(to)
    if not cart_items:
        await db.set_user_state(to, "idle")
        await wa.send_text_message(to, "Your cart is empty. Browse products to start shopping!")
        return
        
    await wa.send_text_message(to, "⏳ Processing your order, please wait...")
    
    order = await wc.create_order(
        phone_number=to,
        customer_name=name,
        cart_items=cart_items,
        address_text=address
    )
    
    # Reset state regardless of outcome
    await db.set_user_state(to, "idle")
    
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

async def process_incoming_message(from_number: str, message: dict, value: dict, action_id: str, incoming_text: str):
    """Processes WhatsApp message in the background to avoid blocking response to Meta."""
    try:
        # Upsert user on every message
        contact_name = None
        contacts = value.get("contacts", [])
        if contacts:
            profile = contacts[0].get("profile", {})
            contact_name = profile.get("name")
        await db.upsert_user(from_number, first_name=contact_name)
        
        # --- Resume bot check (always runs even if paused) ---
        if incoming_text:
            text_lower = incoming_text.lower()
            if text_lower in ["/resume", "resume", "resume bot"]:
                await db.set_bot_paused(from_number, False)
                await db.set_user_state(from_number, "idle")
                await wa.send_text_message(from_number, "✅ Bot resumed. How can I help you?")
                return
                
        is_paused = await db.is_bot_paused(from_number)
        if is_paused:
            logger.info(f"Bot paused for {from_number}. Ignoring message.")
            return
        
        # --- State machine: check if we're waiting for checkout details ---
        user_state = await db.get_user_state(from_number)
        
        if user_state == "checkout_pending" and incoming_text:
            # User is replying with their checkout details
            if incoming_text.lower() in ["cancel", "/cancel", "back"]:
                await db.set_user_state(from_number, "idle")
                await wa.send_text_message(from_number, "Checkout cancelled.")
                await handle_main_menu(from_number)
            else:
                await handle_process_checkout(from_number, incoming_text)
            return
            
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
                
            # Remove product from cart (interactive button support)
            elif action_id.startswith("rmv_"):
                prod_id = int(action_id.split("_")[1])
                await handle_remove_from_cart(from_number, prod_id)
                
            # Menu buttons routing
            elif action_id == "menu_main":
                await handle_main_menu(from_number)
            elif action_id == "menu_categories":
                await handle_categories(from_number)
            elif action_id == "menu_cart":
                await handle_view_cart(from_number)
            elif action_id == "menu_orders":
                await handle_view_orders(from_number)
            elif action_id == "menu_human":
                await db.set_bot_paused(from_number, True)
                agent_phone = os.getenv("HUMAN_AGENT_PHONE", "1234567890")
                msg = (
                    "⏸️ I have paused my automated responses.\n\n"
                    f"Please click this link to chat directly with our human agent on WhatsApp:\n👉 https://wa.me/{agent_phone}\n\n"
                    "Type */resume* when you want me to take over again."
                )
                await wa.send_text_message(from_number, msg)
            elif action_id == "cart_checkout":
                await handle_checkout_prompt(from_number)
            elif action_id == "cart_clear":
                await handle_clear_cart(from_number)
            else:
                await wa.send_text_message(from_number, "I didn't recognize that action. Returning to main menu.")
                await handle_main_menu(from_number)
                
        elif incoming_text:
            logger.info(f"Processing text message from {from_number}")
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
                
            # Add command by typing (e.g. "Add 123")
            elif re.match(r"^add\s+\d+", text_lower):
                try:
                    prod_id = int(re.search(r"\d+", text_lower).group())
                    await handle_add_to_cart(from_number, prod_id)
                except Exception:
                    await wa.send_text_message(from_number, "To add a product, please type *Add [Product ID]* (e.g. *Add 105*).")
                    
            # Remove command by typing (e.g. "Remove 123")
            elif re.match(r"^remove\s+\d+", text_lower):
                try:
                    prod_id = int(re.search(r"\d+", text_lower).group())
                    await handle_remove_from_cart(from_number, prod_id)
                except Exception:
                    await wa.send_text_message(from_number, "To remove an item, type *Remove [Product ID]* (e.g. *Remove 105*).")
                    
            # Pause bot
            elif text_lower in ["/talktohuman", "talk to human", "human", "support"]:
                await db.set_bot_paused(from_number, True)
                await wa.send_text_message(from_number, "⏸️ I have paused my automated responses. A human agent will be with you shortly. Type */resume* when you want me to take over again.")
                
            # Legacy checkout command (still supported)
            elif text_lower.startswith("checkout:"):
                # Strip "Checkout:" prefix and process
                details_text = incoming_text.split(":", 1)[1].strip()
                await handle_process_checkout(from_number, details_text)
                
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

@app.post("/webhook")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
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
    
    msg_id = message.get("id")
    if msg_id and _is_duplicate_message(msg_id):
        logger.info(f"Duplicate message detected: {msg_id}. Ignoring.")
        return JSONResponse({"status": "ignored", "reason": "duplicate"})
        
    msg_type = message.get("type")
    
    # --- Rate Limiting ---
    if _is_rate_limited(from_number):
        logger.warning(f"Rate limited: {from_number}")
        return JSONResponse({"status": "rate_limited"})
    
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
        else:
            logger.warning(f"Unknown interactive type '{int_type}' from {from_number}")
            
    elif msg_type == "text":
        incoming_text = message.get("text", {}).get("body", "").strip()
        # Enforce message length cap
        if len(incoming_text) > MAX_INCOMING_TEXT_LEN:
            incoming_text = incoming_text[:MAX_INCOMING_TEXT_LEN]
    else:
        # Unsupported message types (image, audio, location, etc.)
        logger.info(f"Unsupported message type '{msg_type}' from {from_number}")
        return JSONResponse({"status": "unsupported_type"})

    # Schedule message processing in the background to respond 200 OK immediately to Meta
    background_tasks.add_task(
        process_incoming_message,
        from_number=from_number,
        message=message,
        value=value,
        action_id=action_id,
        incoming_text=incoming_text
    )

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

@app.post("/woo-product-webhook")
async def woo_product_webhook(request: Request):
    """Webhook to receive new/updated products from WooCommerce and embed them in real-time."""
    try:
        product = await request.json()
        logger.info(f"Received WooCommerce product webhook for ID: {product.get('id')}")
        
        if not product.get("id") or not product.get("name"):
            return JSONResponse({"status": "ignored", "reason": "Missing product ID or name"})
            
        prod_id = product.get("id")
        name = product.get("name")
        description = product.get("description", "") or product.get("short_description", "")
        description = re.sub('<[^<]+?>', '', description).strip()
        
        price = product.get("price") or product.get("regular_price") or "0"
        permalink = product.get("permalink", "")
        images = product.get("images", [])
        categories = product.get("categories", [])
        
        doc = {
            "id": prod_id,
            "name": name,
            "description": description,
            "price": float(price) if price else 0.0,
            "permalink": permalink,
            "images": images,
            "categories": categories
        }
        
        text_to_embed = f"{name} {description} {' '.join([c.get('name', '') for c in categories])}"
        embedding = agent._generate_query_embedding(text_to_embed)
        if embedding:
            doc["embedding"] = embedding
            
        success = await db.upsert_product(doc)
        if success:
            logger.info(f"Successfully vectorized and saved product {prod_id} to AI memory.")
        else:
            logger.error(f"Failed to save product {prod_id} to DB.")
            
        return JSONResponse({"status": "ok"})
    except Exception as e:
        logger.error(f"Error processing product webhook: {e}", exc_info=True)
        return JSONResponse({"status": "error"})
