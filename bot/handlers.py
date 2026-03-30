"""
CheapDataNaija Bot — Telegram Handlers
Aiogram 3.x routers for commands, messages, and callback queries.
All menu buttons work directly without AI — AI is only used for free-text chat.
"""

import re
import json
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandStart
from services.llm_service import process_message
from services import wallet_service, smedata_service, paystack_service
from database import (
    get_or_create_user, get_all_plans, get_orders, get_transactions,
    add_or_update_plan, delete_plan, get_profit_stats
)
from config import ADMIN_TELEGRAM_ID

logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    """Check if the user is authorized as an admin."""
    return str(user_id).strip() == str(ADMIN_TELEGRAM_ID).strip()


router = Router()

# ─── In-Memory State for Buy Data Flow ───────────────────────────────────────
# Tracks users who are in the middle of a purchase (waiting for phone number)
_buy_states: dict[int, dict] = {}

# ─── Markdown Safety Helpers ─────────────────────────────────────────────────

def _escape_markdown(text: str) -> str:
    """Escape special Markdown characters for Telegram."""
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


def _back_button():
    """Inline keyboard with just a Back to Menu button."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="menu_main")]
    ])


# ─── Inline Keyboard Menus ───────────────────────────────────────────────────

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
            InlineKeyboardButton(text="🟡 MTN", callback_data="net_MTN"),
            InlineKeyboardButton(text="🔴 Airtel", callback_data="net_AIRTEL"),
        ],
        [
            InlineKeyboardButton(text="🟢 Glo", callback_data="net_GLO"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="menu_main"),
        ],
    ])


def get_funding_menu() -> InlineKeyboardMarkup:
    """Preset funding amount buttons."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="₦500", callback_data="fund_500"),
            InlineKeyboardButton(text="₦1,000", callback_data="fund_1000"),
        ],
        [
            InlineKeyboardButton(text="₦2,000", callback_data="fund_2000"),
            InlineKeyboardButton(text="₦5,000", callback_data="fund_5000"),
        ],
        [
            InlineKeyboardButton(text="₦10,000", callback_data="fund_10000"),
            InlineKeyboardButton(text="💬 Custom Amount", callback_data="fund_custom"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="menu_main"),
        ],
    ])


def _parse_duration(size_name: str) -> str:
    """Parse validity duration from the plan size name."""
    s = size_name.upper()
    if s.endswith("-DAILY"):
        return "1 day"
    elif "-2DAYS" in s:
        return "2 days"
    elif s.endswith("-WEEKLY"):
        return "7 days"
    else:
        return "30 days"


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
    # Clear any pending buy state
    _buy_states.pop(message.from_user.id, None)
    await message.answer(
        "📱 **CheapDataNaija Menu**\n\nSelect an option below:",
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )


@router.message(Command("balance"))
async def cmd_balance(message: Message):
    """Quick balance check — direct, no AI."""
    balance = await wallet_service.check_balance(message.from_user.id)
    await safe_reply(
        message,
        f"💰 **Your Wallet Balance**\n\n"
        f"Balance: **₦{balance:,.2f}**\n\n"
        f"Use 💳 Fund Wallet to top up!",
        reply_markup=_back_button()
    )


@router.message(Command("prices"))
async def cmd_prices(message: Message):
    """Show data prices — direct, no AI."""
    prices = await smedata_service.get_prices()
    text = _format_prices(prices)
    await safe_reply(message, text, reply_markup=_back_button())


@router.message(Command("fund"))
async def cmd_fund(message: Message):
    """Start wallet funding — show amount options."""
    balance = await wallet_service.check_balance(message.from_user.id)
    await safe_reply(
        message,
        f"💳 **Fund Your Wallet**\n\n"
        f"Current Balance: **₦{balance:,.2f}**\n\n"
        f"Select an amount to add:",
        reply_markup=get_funding_menu()
    )


@router.message(Command("orders"))
async def cmd_orders(message: Message):
    """Show order history — direct, no AI."""
    orders = await get_orders(message.from_user.id, limit=10)
    text = _format_orders(orders)
    await safe_reply(message, text, reply_markup=_back_button())


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


# ─── Formatting Helpers ──────────────────────────────────────────────────────

def _format_prices(prices: dict) -> str:
    """Format prices dict into a Telegram-friendly message."""
    if not prices:
        return "📋 No data plans available at the moment. Please try again later."

    text = "📋 **Data Prices**\n\n"

    network_emojis = {"MTN": "🟡", "AIRTEL": "🔴", "GLO": "🟢"}

    for network, plans in sorted(prices.items()):
        emoji = network_emojis.get(network, "📱")
        text += f"{emoji} **{network}**\n"
        # Sort plans by price
        sorted_plans = sorted(plans.items(), key=lambda x: x[1])
        for size, price in sorted_plans:
            duration = _parse_duration(size)
            # Clean up size display
            display_size = size.replace("-", " ").replace("SME MONTHLY", "(SME) 30 days")
            text += f"  • {display_size} — **₦{price:,.0f}** ({duration})\n"
        text += "\n"

    text += "_Use 📦 Buy Data to purchase!_"
    return text


def _format_orders(orders: list) -> str:
    """Format orders list into a Telegram-friendly message."""
    if not orders:
        return (
            "📜 **My Orders**\n\n"
            "You have no orders yet.\n\n"
            "Use 📦 Buy Data to make your first purchase!"
        )

    text = "📜 **My Orders** (Recent)\n\n"
    status_emoji = {
        "completed": "✅",
        "processing": "⏳",
        "pending": "🔄",
        "failed": "❌"
    }

    for o in orders:
        emoji = status_emoji.get(o.get("status", ""), "❓")
        text += (
            f"{emoji} **{o['network']} {o['size']}**\n"
            f"   Phone: {o['phone']} | ₦{o['amount']:,.0f}\n"
            f"   {o.get('created_at', 'N/A')}\n\n"
        )

    return text


def _format_transactions(transactions: list) -> str:
    """Format wallet transactions into a Telegram-friendly message."""
    if not transactions:
        return (
            "📊 **Wallet History**\n\n"
            "No transactions yet.\n\n"
            "Use 💳 Fund Wallet to get started!"
        )

    text = "📊 **Wallet History** (Recent)\n\n"
    for tx in transactions:
        emoji = "💚" if tx.get("type") == "credit" else "🔴"
        sign = "+" if tx.get("type") == "credit" else "-"
        text += (
            f"{emoji} {sign}₦{tx['amount']:,.2f}\n"
            f"   {tx.get('description', 'N/A')}\n"
            f"   {tx.get('created_at', 'N/A')}\n\n"
        )

    return text


# ─── Admin Command Handlers ──────────────────────────────────────────────────

@router.message(Command("syncsetup"))
async def cmd_syncsetup(message: Message):
    """Hidden command to instantly correct the remote database's Plan IDs."""
    if not is_admin(message.from_user.id):
        return
        
    from database import add_or_update_plan, _get_pool
    
    # Clear old plans first to remove stale entries
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM data_plans")
    
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
        
    await message.answer(f"✅ Database synchronized with **{len(full_plans)} plans**! All SMEDATA plans with correct prices + 2% markup injected.", parse_mode="Markdown")

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


# ─── Callback Query Handlers (Menu Buttons — Direct, No AI) ──────────────────

@router.callback_query(F.data == "menu_main")
async def cb_main_menu(callback: CallbackQuery):
    """Return to main menu."""
    # Clear any pending buy state
    _buy_states.pop(callback.from_user.id, None)
    await callback.message.edit_text(
        "📱 **CheapDataNaija Menu**\n\nSelect an option below:",
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )
    await callback.answer()


# ── Check Balance (Direct) ───────────────────────────────────────────────────

@router.callback_query(F.data == "menu_balance")
async def cb_balance(callback: CallbackQuery):
    """Check wallet balance — directly from database."""
    try:
        balance = await wallet_service.check_balance(callback.from_user.id)
        await safe_edit(
            callback.message,
            f"💰 **Your Wallet Balance**\n\n"
            f"Balance: **₦{balance:,.2f}**\n\n"
            f"Use 💳 Fund Wallet to top up!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Fund Wallet", callback_data="menu_fund")],
                [InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="menu_main")],
            ])
        )
    except Exception as e:
        logger.error(f"Balance check error: {e}", exc_info=True)
        await safe_edit(callback.message, "❌ Error checking balance. Please try again.", reply_markup=_back_button())
    await callback.answer()


# ── Data Prices (Direct) ─────────────────────────────────────────────────────

@router.callback_query(F.data == "menu_prices")
async def cb_prices(callback: CallbackQuery):
    """Show all data prices — directly from database."""
    try:
        prices = await smedata_service.get_prices()
        text = _format_prices(prices)
        await safe_edit(callback.message, text, reply_markup=_back_button())
    except Exception as e:
        logger.error(f"Prices error: {e}", exc_info=True)
        await safe_edit(callback.message, "❌ Error loading prices. Please try again.", reply_markup=_back_button())
    await callback.answer()


# ── My Orders (Direct) ───────────────────────────────────────────────────────

@router.callback_query(F.data == "menu_orders")
async def cb_orders(callback: CallbackQuery):
    """Show order history — directly from database."""
    try:
        orders = await get_orders(callback.from_user.id, limit=10)
        text = _format_orders(orders)
        await safe_edit(callback.message, text, reply_markup=_back_button())
    except Exception as e:
        logger.error(f"Orders error: {e}", exc_info=True)
        await safe_edit(callback.message, "❌ Error loading orders. Please try again.", reply_markup=_back_button())
    await callback.answer()


# ── Wallet History (Direct) ──────────────────────────────────────────────────

@router.callback_query(F.data == "menu_history")
async def cb_history(callback: CallbackQuery):
    """Show wallet transaction history — directly from database."""
    try:
        transactions = await wallet_service.get_wallet_history(callback.from_user.id, limit=10)
        text = _format_transactions(transactions)
        await safe_edit(callback.message, text, reply_markup=_back_button())
    except Exception as e:
        logger.error(f"Wallet history error: {e}", exc_info=True)
        await safe_edit(callback.message, "❌ Error loading wallet history. Please try again.", reply_markup=_back_button())
    await callback.answer()


# ── Fund Wallet (Direct — Preset Amounts) ────────────────────────────────────

@router.callback_query(F.data == "menu_fund")
async def cb_fund(callback: CallbackQuery):
    """Show funding amount options."""
    try:
        balance = await wallet_service.check_balance(callback.from_user.id)
        await safe_edit(
            callback.message,
            f"💳 **Fund Your Wallet**\n\n"
            f"Current Balance: **₦{balance:,.2f}**\n\n"
            f"Select an amount to fund:",
            reply_markup=get_funding_menu()
        )
    except Exception as e:
        logger.error(f"Fund menu error: {e}", exc_info=True)
        await safe_edit(callback.message, "❌ Error loading. Please try again.", reply_markup=_back_button())
    await callback.answer()


@router.callback_query(F.data.startswith("fund_"))
async def cb_fund_amount(callback: CallbackQuery):
    """Handle funding amount selection — generate Paystack link directly."""
    amount_str = callback.data.replace("fund_", "")

    if amount_str == "custom":
        # Ask user to type a custom amount
        _buy_states[callback.from_user.id] = {"action": "fund_custom"}
        await safe_edit(
            callback.message,
            "💳 **Custom Funding Amount**\n\n"
            "Type the amount you want to fund (in Naira).\n\n"
            "Example: `2500`",
            reply_markup=_back_button()
        )
        await callback.answer()
        return

    try:
        amount = float(amount_str)
        if amount < 100:
            await safe_edit(callback.message, "⚠️ Minimum funding amount is ₦100.", reply_markup=_back_button())
            await callback.answer()
            return

        telegram_id = callback.from_user.id
        email = f"{telegram_id}@cheapdatanaija.bot"

        result = await paystack_service.initialize_transaction(
            email=email, amount_naira=amount, telegram_id=telegram_id
        )

        if result["success"]:
            await safe_edit(
                callback.message,
                f"💳 **Payment Link Generated!**\n\n"
                f"Amount: **₦{amount:,.0f}**\n\n"
                f"👉 [Click here to pay]({result['authorization_url']})\n\n"
                f"Your wallet will be credited automatically after payment.\n"
                f"Reference: `{result['reference']}`",
                reply_markup=_back_button()
            )
        else:
            await safe_edit(
                callback.message,
                f"❌ Payment error: {result.get('message', 'Unknown error')}\n\nPlease try again.",
                reply_markup=_back_button()
            )
    except Exception as e:
        logger.error(f"Funding error: {e}", exc_info=True)
        await safe_edit(callback.message, "❌ Error generating payment link. Please try again.", reply_markup=_back_button())

    await callback.answer()


# ── Buy Data (Direct — Multi-Step Flow) ──────────────────────────────────────

@router.callback_query(F.data == "menu_buy_data")
async def cb_buy_data(callback: CallbackQuery):
    """Show network selection for data purchase."""
    _buy_states.pop(callback.from_user.id, None)
    await callback.message.edit_text(
        "📦 **Buy Data Bundle**\n\nSelect your network:",
        parse_mode="Markdown",
        reply_markup=get_network_menu()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("net_"))
async def cb_select_network(callback: CallbackQuery):
    """Handle network selection → show plans for that network as buttons."""
    network = callback.data.replace("net_", "").upper()

    try:
        prices = await smedata_service.get_prices(network)

        if not prices or network not in prices:
            await safe_edit(
                callback.message,
                f"❌ No plans available for {network} at the moment.",
                reply_markup=_back_button()
            )
            await callback.answer()
            return

        plans = prices[network]
        # Sort by price and create buttons (2 per row)
        sorted_plans = sorted(plans.items(), key=lambda x: x[1])

        buttons = []
        row = []
        for size, price in sorted_plans:
            duration = _parse_duration(size)
            # Clean up display
            display = size.split("-")[0]  # e.g. "1GB" from "1GB-MONTHLY"
            label = f"{display} ({duration}) — ₦{price:,.0f}"
            # Callback data: buy_{NETWORK}_{SIZE}
            cb_data = f"buy_{network}_{size}"
            row.append(InlineKeyboardButton(text=label, callback_data=cb_data))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        buttons.append([InlineKeyboardButton(text="⬅️ Back", callback_data="menu_buy_data")])

        network_emojis = {"MTN": "🟡", "AIRTEL": "🔴", "GLO": "🟢"}
        emoji = network_emojis.get(network, "📱")

        await safe_edit(
            callback.message,
            f"{emoji} **{network} Data Plans**\n\n"
            f"Select a plan to buy:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    except Exception as e:
        logger.error(f"Network plans error: {e}", exc_info=True)
        await safe_edit(callback.message, "❌ Error loading plans. Please try again.", reply_markup=_back_button())

    await callback.answer()


@router.callback_query(F.data.startswith("buy_"))
async def cb_select_plan(callback: CallbackQuery):
    """Handle plan selection → ask for phone number."""
    parts = callback.data.split("_", 2)  # buy_NETWORK_SIZE
    if len(parts) < 3:
        await callback.answer("Invalid selection", show_alert=True)
        return

    network = parts[1]
    size = parts[2]

    try:
        plan = await smedata_service.get_plan_details(network, size)
        if not plan:
            await callback.answer("Plan not found. Please try again.", show_alert=True)
            return

        price = plan["price"]
        duration = _parse_duration(size)

        # Save state — waiting for phone number
        _buy_states[callback.from_user.id] = {
            "action": "awaiting_phone",
            "network": network,
            "size": size,
            "price": price,
            "duration": duration,
        }

        await safe_edit(
            callback.message,
            f"📦 **Enter Phone Number**\n\n"
            f"Plan: **{size.split('-')[0]} {network}** ({duration})\n"
            f"Price: **₦{price:,.0f}**\n\n"
            f"📱 Type the 11-digit phone number to receive the data:\n\n"
            f"Example: `08012345678`",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Cancel", callback_data="menu_main")],
            ])
        )
    except Exception as e:
        logger.error(f"Plan selection error: {e}", exc_info=True)
        await safe_edit(callback.message, "❌ Error. Please try again.", reply_markup=_back_button())

    await callback.answer()


@router.callback_query(F.data.startswith("confirm_buy_"))
async def cb_confirm_purchase(callback: CallbackQuery):
    """Execute the purchase after confirmation."""
    user_id = callback.from_user.id
    state = _buy_states.get(user_id)

    if not state or state.get("action") != "ready_to_buy":
        await callback.answer("Session expired. Please start over from /menu.", show_alert=True)
        _buy_states.pop(user_id, None)
        return

    network = state["network"]
    size = state["size"]
    phone = state["phone"]
    price = state["price"]
    duration = state["duration"]

    # Clear state immediately to prevent double-buy
    _buy_states.pop(user_id, None)

    try:
        # Get plan details for cost/profit tracking
        plan = await smedata_service.get_plan_details(network, size)
        if not plan:
            await safe_edit(callback.message, "❌ Plan no longer available. Please try again.", reply_markup=_back_button())
            await callback.answer()
            return

        selling_price = plan["price"]
        cost_price = plan["cost_price"]
        profit = selling_price - cost_price

        # Check balance
        balance = await wallet_service.check_balance(user_id)
        if balance < selling_price:
            shortfall = selling_price - balance
            await safe_edit(
                callback.message,
                f"❌ **Insufficient Balance**\n\n"
                f"You need **₦{selling_price:,.0f}** but only have **₦{balance:,.2f}**.\n"
                f"Please fund at least **₦{shortfall:,.0f}** to your wallet first.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💳 Fund Wallet", callback_data="menu_fund")],
                    [InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="menu_main")],
                ])
            )
            await callback.answer()
            return

        # Deduct wallet
        try:
            new_balance = await wallet_service.deduct_wallet(
                user_id, selling_price,
                f"{size} {network} data for {phone}"
            )
        except wallet_service.InsufficientFundsError as e:
            await safe_edit(callback.message, f"❌ {str(e)}", reply_markup=_back_button())
            await callback.answer()
            return

        # Record order
        from database import insert_order, update_order_status
        order_id = await insert_order(
            user_id=user_id, network=network, size=size,
            phone=phone, amount=selling_price,
            cost_price=cost_price, profit=profit,
            status="processing"
        )

        # Show processing message
        await safe_edit(
            callback.message,
            f"⏳ **Processing your order...**\n\n"
            f"Sending {size.split('-')[0]} {network} data to {phone}..."
        )

        # Call SMEDATA API
        result = await smedata_service.buy_data(network, size, phone)

        if result["success"]:
            await update_order_status(order_id, "completed", json.dumps(result.get("details", {})))
            await safe_edit(
                callback.message,
                f"✅ **Purchase Successful!**\n\n"
                f"• **{size.split('-')[0]} {network}** data sent to **{phone}**\n"
                f"• Validity: {duration}\n"
                f"• Amount Charged: ₦{selling_price:,.0f}\n"
                f"• Remaining Balance: ₦{new_balance:,.2f}\n\n"
                f"Thank you for choosing CheapDataNaija! 🎉",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📦 Buy More Data", callback_data="menu_buy_data")],
                    [InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="menu_main")],
                ])
            )
        else:
            # Refund on failure
            await wallet_service.fund_wallet(user_id, selling_price, f"refund_order_{order_id}")
            await update_order_status(order_id, "failed", json.dumps(result))
            await safe_edit(
                callback.message,
                f"❌ **Purchase Failed**\n\n"
                f"{result.get('message', 'Unknown error')}\n\n"
                f"Your wallet has been refunded **₦{selling_price:,.0f}**.",
                reply_markup=_back_button()
            )
    except Exception as e:
        logger.error(f"Purchase execution error: {e}", exc_info=True)
        await safe_edit(
            callback.message,
            "❌ An error occurred during purchase. If you were charged, your wallet will be refunded.",
            reply_markup=_back_button()
        )

    await callback.answer()


@router.callback_query(F.data == "cancel_buy")
async def cb_cancel_buy(callback: CallbackQuery):
    """Cancel the buy flow."""
    _buy_states.pop(callback.from_user.id, None)
    await callback.message.edit_text(
        "📱 **CheapDataNaija Menu**\n\nSelect an option below:",
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )
    await callback.answer()


# ─── General Message Handler (AI Chat + Buy Flow Phone Input) ─────────────────

@router.message(F.text)
async def handle_message(message: Message):
    """Handle all text messages — check for buy flow state first, then forward to AI."""
    user_id = message.from_user.id
    user_text = message.text.strip()

    if not user_text:
        return

    # ── Check if user is in a buy flow (awaiting phone number) ────────────
    state = _buy_states.get(user_id)

    if state and state.get("action") == "fund_custom":
        # User is entering a custom funding amount
        _buy_states.pop(user_id, None)
        try:
            amount = float(user_text.replace(",", "").replace("₦", "").strip())
            if amount < 100:
                await safe_reply(message, "⚠️ Minimum funding amount is **₦100**. Please try again.", reply_markup=_back_button())
                return
            if amount > 1000000:
                await safe_reply(message, "⚠️ Maximum funding amount is **₦1,000,000**.", reply_markup=_back_button())
                return

            email = f"{user_id}@cheapdatanaija.bot"
            result = await paystack_service.initialize_transaction(
                email=email, amount_naira=amount, telegram_id=user_id
            )

            if result["success"]:
                await safe_reply(
                    message,
                    f"💳 **Payment Link Generated!**\n\n"
                    f"Amount: **₦{amount:,.0f}**\n\n"
                    f"👉 [Click here to pay]({result['authorization_url']})\n\n"
                    f"Your wallet will be credited automatically after payment.\n"
                    f"Reference: `{result['reference']}`",
                    reply_markup=_back_button()
                )
            else:
                await safe_reply(
                    message,
                    f"❌ Payment error: {result.get('message', 'Unknown error')}",
                    reply_markup=_back_button()
                )
        except ValueError:
            await safe_reply(message, "⚠️ Please enter a valid number. Example: `2500`", reply_markup=_back_button())
        return

    if state and state.get("action") == "awaiting_phone":
        # User typed a phone number for buying data
        phone = re.sub(r'[^\d]', '', user_text)  # Strip non-digits

        if len(phone) != 11 or not phone.startswith("0"):
            await safe_reply(
                message,
                "⚠️ Please enter a valid **11-digit phone number** starting with **0**.\n\n"
                "Example: `08012345678`",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Cancel", callback_data="menu_main")],
                ])
            )
            return

        # Update state to ready for confirmation
        network = state["network"]
        size = state["size"]
        price = state["price"]
        duration = state["duration"]

        _buy_states[user_id] = {
            **state,
            "action": "ready_to_buy",
            "phone": phone,
        }

        # Show order summary with confirm button
        balance = await wallet_service.check_balance(user_id)

        await safe_reply(
            message,
            f"📋 **Order Summary**\n\n"
            f"• Network: **{network}**\n"
            f"• Data: **{size.split('-')[0]}**\n"
            f"• Validity: **{duration}**\n"
            f"• Phone: **{phone}**\n"
            f"• Price: **₦{price:,.0f}**\n"
            f"• Wallet Balance: **₦{balance:,.2f}**\n\n"
            f"{'✅ Sufficient balance' if balance >= price else '❌ Insufficient balance — please fund your wallet first'}\n\n"
            f"Tap **Confirm** to proceed:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Confirm Purchase", callback_data=f"confirm_buy_{network}_{size}")],
                [InlineKeyboardButton(text="❌ Cancel", callback_data="menu_main")],
            ]) if balance >= price else InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Fund Wallet", callback_data="menu_fund")],
                [InlineKeyboardButton(text="❌ Cancel", callback_data="menu_main")],
            ])
        )
        return

    # ── No active flow — send to AI ──────────────────────────────────────
    logger.info(f"Message from {user_id}: {user_text[:100]}")

    # Send typing indicator
    await message.bot.send_chat_action(message.chat.id, "typing")

    # Process through Groq LLM
    response = await process_message(user_id, user_text)

    # Check if response is an error — attach menu keyboard so user can continue
    is_error = response.startswith(("⏳", "Sorry,"))
    markup = get_main_menu() if is_error else None

    # Send response (split if too long for Telegram's 4096 char limit)
    if len(response) <= 4096:
        await safe_reply(message, response, reply_markup=markup)
    else:
        chunks = [response[i:i+4000] for i in range(0, len(response), 4000)]
        for i, chunk in enumerate(chunks):
            # Attach menu to last chunk only
            await safe_reply(message, chunk, reply_markup=markup if i == len(chunks) - 1 else None)
