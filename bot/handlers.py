"""
CheapDataNaija Bot — Telegram Handlers
Aiogram 3.x routers for commands, messages, and callback queries.
"""

import re
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandStart
from services.llm_service import process_message
from database import get_or_create_user, get_all_plans, add_or_update_plan, delete_plan, get_profit_stats
from config import ADMIN_TELEGRAM_ID

logger = logging.getLogger(__name__)

def is_admin(user_id: int) -> bool:
    """Check if the user is authorized as an admin."""
    return str(user_id).strip() == str(ADMIN_TELEGRAM_ID).strip()

router = Router()


# ─── Markdown Safety Helpers ─────────────────────────────────────────────────

def _escape_markdown(text: str) -> str:
    """Escape special Markdown characters for Telegram."""
    # Telegram Markdown v1 special chars: _ * ` [
    escape_chars = r'_*`['
    return re.sub(r'([' + re.escape(escape_chars) + r'])', r'\\\1', text)


async def safe_reply(message: Message, text: str, reply_markup=None):
    """Send a reply that falls back to plain text if Markdown parsing fails."""
    try:
        await message.answer(text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception as md_err:
        logger.warning(f"Markdown send failed, retrying as plain text: {md_err}")
        try:
            await message.answer(text, parse_mode=None, reply_markup=reply_markup)
        except Exception as plain_err:
            logger.error(f"Plain text send also failed: {plain_err}")
            await message.answer(
                "I processed your request but couldn't format the response. "
                "Please try again or use /menu.",
                reply_markup=reply_markup
            )


async def safe_edit(callback_message: Message, text: str, reply_markup=None):
    """Edit a message that falls back to plain text if Markdown parsing fails."""
    try:
        await callback_message.edit_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception as md_err:
        logger.warning(f"Markdown edit failed, retrying as plain text: {md_err}")
        try:
            await callback_message.edit_text(text, parse_mode=None, reply_markup=reply_markup)
        except Exception as plain_err:
            logger.error(f"Plain text edit also failed: {plain_err}")
            await callback_message.edit_text(
                "I processed your request but couldn't format the response. "
                "Please try again or use /menu.",
                reply_markup=reply_markup
            )

# ─── Inline Keyboard Menu ────────────────────────────────────────────────────

def get_main_menu() -> InlineKeyboardMarkup:
    """Build the main inline keyboard menu."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📦 Buy Data", callback_data="menu_buy_data"),
            InlineKeyboardButton(text="💰 Check Balance", callback_data="menu_balance"),
        ],
        [
            InlineKeyboardButton(text="💳 Fund Wallet", callback_data="menu_fund"),
            InlineKeyboardButton(text="📜 My Orders", callback_data="menu_orders"),
        ],
        [
            InlineKeyboardButton(text="📊 Wallet History", callback_data="menu_history"),
            InlineKeyboardButton(text="📋 Data Prices", callback_data="menu_prices"),
        ],
    ])


def get_network_menu() -> InlineKeyboardMarkup:
    """Menu for selecting a network."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟡 MTN", callback_data="net_mtn"),
            InlineKeyboardButton(text="🔴 Airtel", callback_data="net_airtel"),
        ],
        [
            InlineKeyboardButton(text="🟢 Glo", callback_data="net_glo"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="menu_main"),
        ],
    ])


# ─── Command Handlers ────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message):
    """Handle /start command — welcome message."""
    await get_or_create_user(message.from_user.id)

    welcome = (
        "👋 **Welcome to CheapDataNaija Bot!**\n\n"
        "I help you buy affordable data bundles for MTN, Airtel, and Glo — instantly.\n\n"
        "💡 **How it works:**\n"
        "1️⃣ Fund your wallet once via Paystack\n"
        "2️⃣ Buy data instantly — just type what you need\n"
        "3️⃣ Data is delivered to your phone immediately\n\n"
        "🗣️ **Just talk to me naturally:**\n"
        '• _"I want 2GB MTN data"_\n'
        '• _"Buy 5GB Airtel for 08012345678"_\n'
        '• _"Check my balance"_\n'
        '• _"Fund my wallet with 1000 naira"_\n\n'
        "Or use the menu below for quick access. 👇"
    )

    await message.answer(welcome, parse_mode="Markdown", reply_markup=get_main_menu())


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    """Show the inline menu."""
    await message.answer(
        "📱 **CheapDataNaija Menu**\n\nSelect an option below:",
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )


@router.message(Command("balance"))
async def cmd_balance(message: Message):
    """Quick balance check."""
    response = await process_message(message.from_user.id, "Check my wallet balance")
    await safe_reply(message, response)


@router.message(Command("prices"))
async def cmd_prices(message: Message):
    """Show data prices."""
    response = await process_message(message.from_user.id, "Show me all data prices")
    await safe_reply(message, response)


@router.message(Command("fund"))
async def cmd_fund(message: Message):
    """Start wallet funding."""
    response = await process_message(message.from_user.id, "I want to fund my wallet")
    await safe_reply(message, response)


@router.message(Command("orders"))
async def cmd_orders(message: Message):
    """Show order history."""
    response = await process_message(message.from_user.id, "Show my order history")
    await safe_reply(message, response)


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Show help information."""
    help_text = (
        "ℹ️ **CheapDataNaija Bot — Help**\n\n"
        "**Commands:**\n"
        "/start — Welcome message\n"
        "/menu — Quick menu\n"
        "/balance — Check wallet balance\n"
        "/prices — View data prices\n"
        "/fund — Fund your wallet\n"
        "/orders — Order history\n"
        "/help — This help message\n\n"
        "**Or just type naturally:**\n"
        '• _"Buy 1GB MTN data for 08012345678"_\n'
        '• _"How much is 5GB Airtel?"_\n'
        '• _"Fund my wallet with 2000 naira"_\n'
        '• _"Show my balance"_\n\n'
        "I understand natural language, so just tell me what you need!"
    )
    await message.answer(help_text, parse_mode="Markdown")


# ─── Admin Command Handlers ──────────────────────────────────────────────────

@router.message(Command("syncsetup"))
async def cmd_syncsetup(message: Message):
    """Hidden command to instantly correct the remote database's Plan IDs."""
    if not is_admin(message.from_user.id):
        return
        
    from database import add_or_update_plan, _get_db
    
    # Clear old plans first to remove stale entries
    db = await _get_db()
    try:
        await db.execute("DELETE FROM data_plans")
        await db.commit()
    finally:
        await db.close()
    
    # Full catalog matching SMEDATA API docs + website prices
    full_plans = [
        # MTN Data Share (SME) — 30 days
        ("MTN", "1", "1GB-SME", "1gb", 600),
        ("MTN", "1", "2GB-SME", "2gb", 1200),
        ("MTN", "1", "3GB-SME", "3gb", 1800),
        ("MTN", "1", "5GB-SME", "5gb", 3000),
        # MTN Direct Data
        ("MTN", "1", "230MB-DAILY", "230mb1d", 200),
        ("MTN", "1", "1GB-DAILY", "1gb1d", 486),
        ("MTN", "1", "1.5GB-2DAYS", "1.5gb2d", 585),
        ("MTN", "1", "1GB-WEEKLY", "1gb1w", 785),
        ("MTN", "1", "2.5GB-DAILY", "2.5gb1d", 600),
        ("MTN", "1", "2.5GB-2DAYS", "2.5gb2d", 885),
        ("MTN", "1", "1.5GB-WEEKLY", "1.5gb1w", 980),
        ("MTN", "1", "2GB-MONTHLY", "2gb1m", 1465),
        ("MTN", "1", "2.7GB-MONTHLY", "2.7gb1m", 1950),
        ("MTN", "1", "6GB-WEEKLY", "6gb1w", 2430),
        ("MTN", "1", "3.5GB-MONTHLY", "3.5gb1m", 2450),
        ("MTN", "1", "7GB-MONTHLY", "7gb1m", 3420),
        ("MTN", "1", "10GB-MONTHLY", "10gb1m", 4400),
        ("MTN", "1", "12.5GB-MONTHLY", "12.5gb1m", 5400),
        ("MTN", "1", "16.5GB-MONTHLY", "16.5gb1m", 6350),
        ("MTN", "1", "20GB-MONTHLY", "20gb1m", 7350),
        ("MTN", "1", "25GB-MONTHLY", "25gb1m", 8800),
        # Airtel Direct Data
        ("AIRTEL", "2", "300MB-2DAYS", "300mb2d", 297),
        ("AIRTEL", "2", "500MB-WEEKLY", "500mb1w", 490),
        ("AIRTEL", "2", "1.5GB-2DAYS", "1.5gb2d", 590),
        ("AIRTEL", "2", "1GB-WEEKLY", "1gb1w", 780),
        ("AIRTEL", "2", "1.5GB-WEEKLY", "1.5gb1w", 980),
        ("AIRTEL", "2", "3.5GB-WEEKLY", "3.5gb1w", 1470),
        ("AIRTEL", "2", "2GB-MONTHLY", "2gb1m", 1480),
        ("AIRTEL", "2", "3GB-MONTHLY", "3gb1m", 1970),
        ("AIRTEL", "2", "6GB-WEEKLY", "6gb1w", 2450),
        ("AIRTEL", "2", "4GB-MONTHLY", "4gb1m", 2470),
        ("AIRTEL", "2", "10GB-WEEKLY", "10gb1w", 2950),
        ("AIRTEL", "2", "8GB-MONTHLY", "8gb1m", 2970),
        ("AIRTEL", "2", "10GB-MONTHLY", "10gb1m", 3930),
        ("AIRTEL", "2", "15GB-WEEKLY", "15gb1w", 4870),
        ("AIRTEL", "2", "13GB-MONTHLY", "13gb1m", 4900),
        ("AIRTEL", "2", "18GB-MONTHLY", "18gb1m", 5880),
        ("AIRTEL", "2", "25GB-MONTHLY", "25gb1m", 7830),
        ("AIRTEL", "2", "35GB-MONTHLY", "35gb1m", 9770),
        # GLO CG Data — 30 days
        ("GLO", "3", "500MB-MONTHLY", "500MB", 280),
        ("GLO", "3", "1GB-MONTHLY", "1GB", 480),
        ("GLO", "3", "2GB-MONTHLY", "2GB", 960),
        ("GLO", "3", "3GB-MONTHLY", "3GB", 1440),
        ("GLO", "3", "5GB-MONTHLY", "5GB", 2400),
        ("GLO", "3", "10GB-MONTHLY", "10GB", 4800),
    ]
    
    for net, nid, size, pid, cost in full_plans:
        await add_or_update_plan(net, nid, size, pid, cost)
        
    await message.answer(f"✅ Database synchronized with **{len(full_plans)} plans**! All SMEDATA plans with correct prices + 10% markup injected.", parse_mode="Markdown")

@router.message(Command("myid"))
async def cmd_myid(message: Message):
    """Temporary command to get user ID for setting up config."""
    await message.answer(f"Your Telegram User ID is: `{message.from_user.id}`", parse_mode="Markdown")


@router.message(Command("listplans"))
async def cmd_listplans(message: Message):
    """List all available data plans."""
    if not is_admin(message.from_user.id):
        return
        
    plans = await get_all_plans()
    if not plans:
        await message.answer("No data plans found in the database. Use /addplan to add some.")
        return
        
    response = "📋 **Live Data Plans Catalog**\n\n"
    for p in plans:
        response += f"• **{p['network']} {p['size']}** (NID:{p['network_id']}, PID:{p['plan_id']}): ₦{p['price']:,.2f}\n"
        
    await message.answer(response, parse_mode="Markdown")


@router.message(Command("addplan"))
async def cmd_addplan(message: Message):
    """Add or update a data plan."""
    if not is_admin(message.from_user.id):
        return
        
    parts = message.text.split()[1:]
    if len(parts) != 5:
        await message.answer(
            "⚠️ **Format Error**\n"
            "Usage: `/addplan <Network> <NetworkID> <Size> <PlanID> <Price>`\n"
            "Example: `/addplan MTN 1 20GB 11 4900`",
            parse_mode="Markdown"
        )
        return
        
    network, network_id, size, plan_id, price_str = parts
    try:
        price = float(price_str)
        await add_or_update_plan(network, network_id, size, plan_id, price)
        await message.answer(f"✅ Successfully added/updated the **{network.upper()} {size.upper()}** plan for ₦{price:,.2f}.", parse_mode="Markdown")
    except ValueError:
        await message.answer("⚠️ Ensure the price is a valid number.")
    except Exception as e:
        await message.answer(f"❌ Error saving plan: {str(e)}")


@router.message(Command("delplan"))
async def cmd_delplan(message: Message):
    """Delete a data plan."""
    if not is_admin(message.from_user.id):
        return
        
    parts = message.text.split()[1:]
    if len(parts) != 2:
        await message.answer(
            "⚠️ **Format Error**\n"
            "Usage: `/delplan <Network> <Size>`\n"
            "Example: `/delplan MTN 20GB`",
            parse_mode="Markdown"
        )
        return
        
    network, size = parts
    deleted = await delete_plan(network, size)
    if deleted:
        await message.answer(f"🗑️ Successfully deleted the **{network.upper()} {size.upper()}** plan.", parse_mode="Markdown")
    else:
        await message.answer(f"⚠️ Plan **{network.upper()} {size.upper()}** not found.")


@router.message(Command("gains"))
async def cmd_gains(message: Message):
    """Show profit/gains report for the admin."""
    if not is_admin(message.from_user.id):
        return

    stats = await get_profit_stats()

    def fmt(period: dict) -> str:
        return (
            f"  📈 Revenue: ₦{period['total_revenue']:,.2f}\n"
            f"  💸 Cost: ₦{period['total_cost']:,.2f}\n"
            f"  💰 Profit: ₦{period['total_profit']:,.2f}\n"
            f"  🛒 Orders: {period['order_count']}"
        )

    report = (
        "📊 **CheapDataNaija — Gains Report**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🗓️ **Today**\n{fmt(stats['today'])}\n\n"
        f"📅 **This Week** (7 days)\n{fmt(stats['week'])}\n\n"
        f"🗓️ **This Month**\n{fmt(stats['month'])}\n\n"
        f"📆 **This Year**\n{fmt(stats['year'])}\n\n"
        f"🏆 **All Time**\n{fmt(stats['all_time'])}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Total Users: {stats['total_users']}"
    )

    await message.answer(report, parse_mode="Markdown")


# ─── Callback Query Handlers (Menu Buttons) ──────────────────────────────────

@router.callback_query(F.data == "menu_main")
async def cb_main_menu(callback: CallbackQuery):
    """Return to main menu."""
    await callback.message.edit_text(
        "📱 **CheapDataNaija Menu**\n\nSelect an option below:",
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )
    await callback.answer()


@router.callback_query(F.data == "menu_buy_data")
async def cb_buy_data(callback: CallbackQuery):
    """Show network selection for data purchase."""
    await callback.message.edit_text(
        "📦 **Buy Data Bundle**\n\nSelect your network:",
        parse_mode="Markdown",
        reply_markup=get_network_menu()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("net_"))
async def cb_select_network(callback: CallbackQuery):
    """Handle network selection → show prices via AI."""
    network_map = {"net_mtn": "MTN", "net_airtel": "Airtel", "net_glo": "Glo"}
    network = network_map.get(callback.data, "MTN")
    response = await process_message(
        callback.from_user.id,
        f"Show me {network} data prices and let me pick a plan to buy"
    )
    await safe_edit(callback.message, response)
    await callback.answer()


@router.callback_query(F.data == "menu_balance")
async def cb_balance(callback: CallbackQuery):
    """Check wallet balance."""
    response = await process_message(callback.from_user.id, "Check my wallet balance")
    await safe_edit(
        callback.message, response,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="menu_main")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "menu_fund")
async def cb_fund(callback: CallbackQuery):
    """Fund wallet prompt."""
    response = await process_message(callback.from_user.id, "I want to fund my wallet")
    await safe_edit(callback.message, response)
    await callback.answer()


@router.callback_query(F.data == "menu_orders")
async def cb_orders(callback: CallbackQuery):
    """Show order history."""
    response = await process_message(callback.from_user.id, "Show my recent orders")
    await safe_edit(
        callback.message, response,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="menu_main")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "menu_history")
async def cb_history(callback: CallbackQuery):
    """Show wallet transaction history."""
    response = await process_message(callback.from_user.id, "Show my wallet history")
    await safe_edit(
        callback.message, response,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="menu_main")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "menu_prices")
async def cb_prices(callback: CallbackQuery):
    """Show all data prices."""
    response = await process_message(callback.from_user.id, "Show me all data prices for all networks")
    await safe_edit(
        callback.message, response,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="menu_main")]
        ])
    )
    await callback.answer()


# ─── General Message Handler (AI Conversation) ───────────────────────────────

@router.message(F.text)
async def handle_message(message: Message):
    """Handle all text messages — forward to Groq AI."""
    user_id = message.from_user.id
    user_text = message.text.strip()

    if not user_text:
        return

    logger.info(f"Message from {user_id}: {user_text[:100]}")

    # Send typing indicator
    await message.bot.send_chat_action(message.chat.id, "typing")

    # Process through Groq LLM
    response = await process_message(user_id, user_text)

    # Send response (split if too long for Telegram's 4096 char limit)
    if len(response) <= 4096:
        await safe_reply(message, response)
    else:
        # Split into chunks
        chunks = [response[i:i+4000] for i in range(0, len(response), 4000)]
        for chunk in chunks:
            await safe_reply(message, chunk)
