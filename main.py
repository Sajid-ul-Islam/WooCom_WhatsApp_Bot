import os
import json
import asyncio
import hmac
import hashlib
import base64
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
from middleware import is_rate_limited, is_duplicate_message, load_dedup_ids_from_db, MAX_INCOMING_TEXT_LEN
from wit_client import WitClient

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("whatsapp_bot")

load_dotenv()

# Database client (created early, before lifespan)
db = DatabaseClient()

# Bot context — initialized during app lifespan with all clients
ctx: BotContext | None = None

# Graceful shutdown event for background workers
_shutdown_event = asyncio.Event()


# ==================== SECURITY HELPERS ====================


def verify_meta_webhook_signature(raw_body: bytes, signature_header: str) -> bool:
    """
    Verify Meta's X-Hub-Signature-256 header using the App Secret.
    If no App Secret is configured, skip verification (fallback mode).
    """
    app_secret = os.getenv("WHATSAPP_APP_SECRET", "")
    if not app_secret:
        logger.warning("WHATSAPP_APP_SECRET not set — webhook signature verification disabled.")
        return True

    if not signature_header:
        logger.error("Missing X-Hub-Signature-256 header.")
        return False

    expected = "sha256=" + hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, signature_header)


def verify_admin_auth(request: Request) -> bool:
    """Check if the request has a valid admin API key."""
    admin_key = os.getenv("ADMIN_API_KEY", "")
    if not admin_key:
        logger.warning("ADMIN_API_KEY not set — admin endpoints are unprotected.")
        return True  # No key configured = open access (backward compatible)

    # Check Authorization header first
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return hmac.compare_digest(auth_header[7:], admin_key)

    # Fall back to query parameter
    query_key = request.query_params.get("api_key", "")
    return hmac.compare_digest(query_key, admin_key)


def verify_woo_webhook(request: Request, raw_body: bytes) -> bool:
    """Verify WooCommerce webhook signature if a secret is configured.
    
    WooCommerce signs webhooks using HMAC-SHA256 with the secret,
    then base64-encodes the digest and sends it as X-WC-Webhook-Signature.
    """
    webhook_secret = os.getenv("WOOCOMMERCE_WEBHOOK_SECRET", "")
    if not webhook_secret:
        return True  # No secret configured = accept all

    # WooCommerce sends signature in the X-WC-Webhook-Signature header
    signature = request.headers.get("X-WC-Webhook-Signature", "")
    if not signature:
        logger.error("Missing X-WC-Webhook-Signature header.")
        return False

    expected = base64.b64encode(
        hmac.new(webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    ).decode()
    return hmac.compare_digest(expected, signature)


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
    wit_client = WitClient()
    if wit_client.configured:
        logger.info(f"Wit.ai client initialized with server token (starts with: {wit_client._token[:6]}...)")

    ctx = BotContext(
        db=db,
        wc=WooCommerceClient(),
        wa=WhatsAppClient(),
        agent=RAGAgent(db_client=db),
        wit=wit_client,
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

    # --- Load dedup IDs from Supabase into memory ---
    try:
        recent_ids = await db.load_recent_processed_ids()
        load_dedup_ids_from_db(recent_ids)
    except Exception as e:
        logger.warning(f"Could not load recent processed IDs from Supabase: {e}")

    # --- Reprocess any pending messages from a previous crash ---
    try:
        pending = await db.get_unprocessed_pending_messages()
        if pending:
            logger.info(f"Found {len(pending)} unprocessed pending messages. Reprocessing...")
            for msg in pending:
                claimed = await db.claim_pending_message(msg["id"])
                if claimed:
                    payload = msg.get("payload", {})
                    asyncio.create_task(
                        process_incoming_message(
                            ctx=ctx,
                            from_number=payload.get("from_number", ""),
                            message=payload.get("message", {}),
                            value=payload.get("value", {}),
                            action_id=payload.get("action_id", ""),
                            incoming_text=payload.get("incoming_text", ""),
                            pending_id=msg["id"]
                        )
                    )
    except Exception as e:
        logger.warning(f"Could not reprocess pending messages: {e}")

    # Reset shutdown event
    _shutdown_event.clear()

    # --- Start Abandoned Cart Worker ---
    async def abandoned_cart_worker():
        while True:
            try:
                # Wait 1 hour, or until shutdown is requested
                try:
                    await asyncio.wait_for(_shutdown_event.wait(), timeout=3600)
                    logger.info("Abandoned cart worker shutting down gracefully...")
                    return
                except asyncio.TimeoutError:
                    pass  # Normal timeout, run the check

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
            except asyncio.CancelledError:
                logger.info("Abandoned cart worker cancelled. Exiting...")
                return
            except Exception as e:
                logger.error(f"Abandoned cart worker error: {e}")

    # Fire and forget the background task
    asyncio.create_task(abandoned_cart_worker())

    yield

    # Signal shutdown to background workers
    _shutdown_event.set()

    # Cleanup HTTP clients on shutdown
    await ctx.wc.close()
    await ctx.wa.close()
    if ctx.wit:
        await ctx.wit.close()
    logger.info("WhatsApp WooCommerce Bot is shutting down...")


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def health_check():
    """Root health check — confirms the app is running."""
    return {"status": "ok", "service": "WooCom WhatsApp Bot"}


@app.get("/api/dashboard-stats")
async def api_dashboard_stats(request: Request):
    """Returns real-time dashboard statistics from Supabase."""
    if not verify_admin_auth(request):
        raise HTTPException(status_code=401, detail="Unauthorized. Provide a valid API key via ?api_key= or Authorization: Bearer header.")
    stats = await db.get_dashboard_stats()
    return JSONResponse(content=stats)


@app.get("/api/wit-stats")
async def api_wit_stats(request: Request):
    """Returns Wit.ai classification statistics."""
    if not verify_admin_auth(request):
        raise HTTPException(status_code=401, detail="Unauthorized. Provide a valid API key via ?api_key= or Authorization: Bearer header.")
    if not ctx or not ctx.wit:
        return JSONResponse(content={"configured": False, "total_calls": 0, "intents": {}})
    return JSONResponse(content={
        "configured": ctx.wit.configured,
        **ctx.wit.stats.snapshot()
    })


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
async def broadcast_message(request: Request, req: BroadcastRequest):
    """Sends a promotional message to all active users."""
    if not verify_admin_auth(request):
        raise HTTPException(status_code=401, detail="Unauthorized. Provide a valid API key via ?api_key= or Authorization: Bearer header.")

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
            await asyncio.sleep(1.5)  # Increased delay to respect Meta API rate limits
        except Exception as e:
            logger.error(f"Broadcast failed for {phone}: {e}")
            await asyncio.sleep(2)  # Back off on errors

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
    """Meta webhook POST receiver endpoint with signature verification."""
    # Read raw body for signature verification before JSON parsing
    raw_body = await request.body()

    # Verify webhook signature
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_meta_webhook_signature(raw_body, signature):
        logger.error("Webhook signature verification failed. Possible spoofing attempt.")
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse incoming JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    except Exception as e:
        logger.error(f"Unexpected error parsing webhook: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")

    # Log incoming webhook JSON for debugging
    logger.debug(f"Webhook received: {json.dumps(body)[:500]}")

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

    # --- Check duplicate (in-memory fast path) ---
    if msg_id and is_duplicate_message(msg_id):
        logger.info(f"Duplicate message detected: {msg_id}. Ignoring.")
        return JSONResponse({"status": "ignored", "reason": "duplicate"})

    # --- Also check Supabase for cross-restart dedup ---
    if msg_id:
        try:
            is_dup = await db.is_duplicate_message(msg_id)
            if is_dup:
                logger.info(f"Supabase dedup hit for {msg_id}. Ignoring.")
                return JSONResponse({"status": "ignored", "reason": "duplicate_persistent"})
            # Write to Supabase asynchronously (don't wait for the response)
            asyncio.create_task(db.mark_message_processed(msg_id))
        except Exception as e:
            logger.warning(f"Supabase dedup check failed for {msg_id}: {e}")

    msg_type = message.get("type")

    # --- Rate Limiting (in-memory fast path) ---
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

    # --- Create durable pending message (prevents message loss if server crashes during bg processing) ---
    try:
        pending_id = await db.create_pending_message(
            msg_id=msg_id,
            phone_number=from_number,
            payload={
                "from_number": from_number,
                "message": message,
                "value": value,
                "action_id": action_id,
                "incoming_text": incoming_text
            }
        )
    except Exception as e:
        logger.warning(f"Failed to create pending message for {msg_id}: {e}")
        pending_id = None

    # Schedule message processing in the background to respond 200 OK immediately to Meta
    background_tasks.add_task(
        process_incoming_message,
        ctx=ctx,
        from_number=from_number,
        message=message,
        value=value,
        action_id=action_id,
        incoming_text=incoming_text,
        pending_id=pending_id
    )

    return JSONResponse({"status": "ok"})


@app.post("/woo-webhook")
async def woo_webhook(request: Request):
    """Webhook to receive order updates from WooCommerce and notify users via WhatsApp."""
    raw_body = await request.body()

    # Verify WooCommerce webhook signature
    if not verify_woo_webhook(request, raw_body):
        logger.error("WooCommerce webhook signature verification failed.")
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    try:
        body = json.loads(raw_body)
        logger.info(f"WooCommerce order webhook received. Order ID: {body.get('id')}")

        status = body.get("status")
        billing = body.get("billing", {})
        phone = billing.get("phone")
        order_id = body.get("id")

        if phone and status and order_id:
            message = f"🔔 *Order Update*\n\nYour order #{order_id} is now: *{status.upper()}*."
            await ctx.wa.send_text_message(phone, message)

        return JSONResponse({"status": "ok"})
    except json.JSONDecodeError:
        logger.error("Invalid JSON in WooCommerce webhook")
        return JSONResponse({"status": "error", "detail": "Invalid JSON"})
    except Exception as e:
        logger.error(f"Error processing WooCommerce order webhook: {e}")
        return JSONResponse({"status": "error"})


@app.post("/woo-product-webhook")
async def woo_product_webhook(request: Request):
    """Webhook to receive new/updated products from WooCommerce and embed them in real-time."""
    raw_body = await request.body()

    # Verify WooCommerce webhook signature
    if not verify_woo_webhook(request, raw_body):
        logger.error("WooCommerce product webhook signature verification failed.")
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    try:
        product = json.loads(raw_body)
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
    except json.JSONDecodeError:
        logger.error("Invalid JSON in WooCommerce product webhook")
        return JSONResponse({"status": "error", "detail": "Invalid JSON"})
    except Exception as e:
        logger.error(f"Error processing product webhook: {e}", exc_info=True)
        return JSONResponse({"status": "error"})
