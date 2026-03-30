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
from database import get_or_create_user, get_all_plans, add_or_update_plan, delete_plan
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
        
    correct_plans = [
        ("MTN", "1GB", "1gb"), ("MTN", "2GB", "2gb"), ("MTN", "3GB", "3gb"), 
        ("MTN", "5GB", "5gb"), ("MTN", "10GB", "10gb1m"),
        ("AIRTEL", "1GB", "1gb1w"), ("AIRTEL", "2GB", "2gb1m"), ("AIRTEL", "3GB", "3gb1m"), ("AIRTEL", "5GB", "5gb1m"),
        ("GLO", "1GB", "1GB"), ("GLO", "2GB", "2GB"), ("GLO", "3GB", "3GB"), ("GLO", "5GB", "5GB")
    ]
    
    import aiosqlite
    from config import DATABASE_PATH
    db = await aiosqlite.connect(DATABASE_PATH)
    try:
        for net, size, pid in correct_plans:
            await db.execute("UPDATE data_plans SET plan_id=? WHERE network=? AND size=?", (pid, net, size))
        await db.commit()
    finally:
        await db.close()
        
    await message.answer("✅ Database synchronized! The exact SMEDATA Plan IDs have been injected into your live Render bot.", parse_mode="Markdown")

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
