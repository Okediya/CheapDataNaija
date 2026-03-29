"""
CheapDataNaija Bot — Main Entry Point
Webhook server using aiohttp + aiogram 3.x.
Handles Telegram webhook and Paystack webhook endpoints.
"""

import json
import logging
import asyncio
import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update

from config import BOT_TOKEN, WEBHOOK_URL, WEBHOOK_PATH, SERVER_PORT
from database import init_db
from bot.handlers import router
from services.paystack_service import validate_webhook_signature, process_webhook_event
from services.wallet_service import fund_wallet

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─── Bot & Dispatcher ────────────────────────────────────────────────────────

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
)
dp = Dispatcher()
dp.include_router(router)


# ─── Telegram Webhook Handler ────────────────────────────────────────────────

async def handle_telegram_webhook(request: web.Request) -> web.Response:
    """Process incoming Telegram updates via webhook."""
    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
    except Exception as e:
        logger.error(f"Telegram webhook error: {e}", exc_info=True)
    return web.Response(status=200)


# ─── Paystack Webhook Handler ────────────────────────────────────────────────

async def handle_paystack_webhook(request: web.Request) -> web.Response:
    """Process incoming Paystack webhook events."""
    try:
        # Read raw body for signature verification
        body = await request.read()
        signature = request.headers.get("x-paystack-signature", "")

        # Validate signature
        if not validate_webhook_signature(body, signature):
            logger.warning("Invalid Paystack webhook signature.")
            return web.Response(status=401, text="Invalid signature")

        payload = json.loads(body)
        result = await process_webhook_event(payload)

        # Credit wallet on successful charge
        if result.get("event") == "charge.success" and result.get("success"):
            telegram_id = result.get("telegram_id")
            amount = result.get("amount")
            reference = result.get("reference")

            if telegram_id and amount:
                new_balance = await fund_wallet(int(telegram_id), amount, reference)
                logger.info(f"Wallet funded via webhook: user {telegram_id}, +₦{amount:,.2f}, balance ₦{new_balance:,.2f}")

                # Notify user in Telegram
                try:
                    await bot.send_message(
                        int(telegram_id),
                        f"✅ **Wallet Funded Successfully!**\n\n"
                        f"• Amount: ₦{amount:,.2f}\n"
                        f"• New Balance: ₦{new_balance:,.2f}\n"
                        f"• Reference: `{reference}`\n\n"
                        f"You can now buy data instantly. Just tell me what you need!",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify user {telegram_id}: {e}")

        return web.Response(status=200, text="OK")

    except Exception as e:
        logger.error(f"Paystack webhook error: {e}", exc_info=True)
        return web.Response(status=500, text="Error")


# ─── SMEDATA Webhook Handler ──────────────────────────────────────────────────

async def handle_smedata_webhook(request: web.Request) -> web.Response:
    """Process incoming SMEDATA webhook events."""
    try:
        if request.method == "POST":
            try:
                data = await request.json()
            except Exception:
                data = await request.post()
        else:
            data = request.query

        logger.info(f"SMEDATA Webhook received: {dict(data)}")

        # TODO: Implement refund logic based on data['status'] and data['ref']
        # once the exact webhook structure is confirmed in logs.

        return web.Response(status=200, text="OK")

    except Exception as e:
        logger.error(f"SMEDATA webhook error: {e}", exc_info=True)
        return web.Response(status=500, text="Error")


# ─── Health Check ─────────────────────────────────────────────────────────────

async def handle_health(request: web.Request) -> web.Response:
    """Health check endpoint."""
    return web.Response(text="CheapDataNaija Bot is running!", status=200)


# ─── Keep-Alive (prevents Render free tier spin-down) ────────────────────────

async def keep_alive(app: web.Application):
    """Ping own health endpoint every 10 minutes to prevent Render free tier spin-down."""
    import httpx
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if not render_url:
        logger.info("No RENDER_EXTERNAL_URL set — keep-alive disabled (local dev).")
        return
    health_url = f"{render_url}/health"
    logger.info(f"Keep-alive started: pinging {health_url} every 10 minutes.")
    while True:
        await asyncio.sleep(600)  # 10 minutes
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(health_url)
                logger.debug(f"Keep-alive ping: {resp.status_code}")
        except Exception as e:
            logger.warning(f"Keep-alive ping failed: {e}")


# ─── Startup / Shutdown ──────────────────────────────────────────────────────

async def on_startup(app: web.Application):
    """Initialize database and set Telegram webhook."""
    await init_db()
    logger.info("Database initialized.")

    # Set webhook
    await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
    logger.info(f"Webhook set to: {WEBHOOK_URL}")

    # Start keep-alive background task
    app["keep_alive_task"] = asyncio.create_task(keep_alive(app))


async def on_shutdown(app: web.Application):
    """Clean up on shutdown."""
    # Cancel keep-alive
    task = app.get("keep_alive_task")
    if task:
        task.cancel()

    await bot.delete_webhook()
    await bot.session.close()
    logger.info("Bot shut down cleanly.")


# ─── App Factory ──────────────────────────────────────────────────────────────

def create_app() -> web.Application:
    """Create and configure the aiohttp web application."""
    app = web.Application()

    # Routes
    app.router.add_post(WEBHOOK_PATH, handle_telegram_webhook)
    app.router.add_post("/webhook/paystack", handle_paystack_webhook)
    
    # SMEDATA might send POST or GET, so we bind both
    app.router.add_post("/webhook/smedata", handle_smedata_webhook)
    app.router.add_get("/webhook/smedata", handle_smedata_webhook)

    app.router.add_get("/", handle_health)
    app.router.add_get("/health", handle_health)

    # Lifecycle
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    return app


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = create_app()
    logger.info(f"Starting CheapDataNaija Bot on port {SERVER_PORT}...")
    web.run_app(app, host="0.0.0.0", port=SERVER_PORT)
