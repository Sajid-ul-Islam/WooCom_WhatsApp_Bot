import os
import json
import asyncio
import logging
from contextlib import asynccontextmanager
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, PlainTextResponse, HTMLResponse

from db import DatabaseClient
from context import BotContext
from whatsapp_client import WhatsAppClient
from woocommerce_client import WooCommerceClient
from rag_agent import RAGAgent
from handlers import process_incoming_message, handle_main_menu
from middleware import is_rate_limited, is_duplicate_message, MAX_INCOMING_TEXT_LEN

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("whatsapp_bot")

load_dotenv()

# Database client (created early, before lifespan)
db = DatabaseClient()

# Bot context — initialized during app lifespan with all clients
ctx: BotContext | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events: load secrets from Supabase, verify config, warm up clients."""
    global ctx  # noqa: PLW0603

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
    ctx = BotContext(
        db=db,
        wc=WooCommerceClient(),
        wa=WhatsAppClient(),
        agent=RAGAgent(db_client=db),
    )

    # --- Verify config ---
    verify_token = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN")
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN")

    if not verify_token or not phone_id or not access_token:
        logger.error("WhatsApp credentials missing. Check Supabase 'config' table or env vars.")
    else:
        logger.info(f"WhatsApp Client configured for Phone ID: {phone_id}")

    logger.info(f"WooCommerce URL: {os.getenv('WOOCOMMERCE_URL', 'not set')}")
    logger.info(f"LLM Provider: {os.getenv('LLM_PROVIDER', 'not set')}")

    if not db.client:
        logger.error("Supabase client not initialized. Database and carts will not function.")

    # --- Start Abandoned Cart Worker ---
    async def abandoned_cart_worker():
        while True:
            try:
                # Run every 1 hour (3600 seconds)
                await asyncio.sleep(3600)
                
                cohorts = [
                    (1, "🛒 *You left items in your cart!*\n\nComplete your order today to enjoy fast delivery. Reply with *Cart* to view your items!"),
                    (24, "🛒 *Friendly Reminder!*\n\nYour cart is still waiting for you. Would you like to complete your order?\n\nReply with *Cart* to view your items, or browse more to add others!"),
                    (72, "🛒 *Last Chance!*\n\nWe are holding your items for a little longer. Complete your purchase now before they sell out!\n\nReply with *Cart* to view your items and check out.")
                ]
                
                for hours_cohort, msg in cohorts:
                    abandoned = await db.get_abandoned_carts(hours=hours_cohort)
                    for cart in abandoned:
                        phone = cart.get("phone_number")
                        if phone:
                            await ctx.wa.send_text_message(phone, msg)
                            await asyncio.sleep(1)  # Prevent rate limiting
            except Exception as e:
                logger.error(f"Abandoned cart worker error: {e}")

    # Fire and forget the background task
    asyncio.create_task(abandoned_cart_worker())

    yield

    # Cleanup HTTP clients on shutdown
    await ctx.wc.close()
    await ctx.wa.close()
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
            await ctx.wa.send_text_message(phone, req.message)
            count += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Broadcast failed for {phone}: {e}")

    return JSONResponse({"status": "ok", "message": f"Broadcast sent to {count} users."})


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
    if msg_id and is_duplicate_message(msg_id):
        logger.info(f"Duplicate message detected: {msg_id}. Ignoring.")
        return JSONResponse({"status": "ignored", "reason": "duplicate"})

    msg_type = message.get("type")

    # --- Rate Limiting ---
    if is_rate_limited(from_number):
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
        ctx=ctx,
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
            await ctx.wa.send_text_message(phone, message)

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

        from utils import clean_html

        prod_id = product.get("id")
        name = product.get("name")
        description = product.get("description", "") or product.get("short_description", "")
        description = clean_html(description)

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
        embedding = ctx.agent._generate_query_embedding(text_to_embed)
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
