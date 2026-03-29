"""
CheapDataNaija Bot — Telegram Handlers
Aiogram 3.x routers for commands, messages, and callback queries.
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandStart
from services.gemini_service import process_message
from database import get_or_create_user

logger = logging.getLogger(__name__)

router = Router()

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
    await message.answer(response, parse_mode="Markdown")


@router.message(Command("prices"))
async def cmd_prices(message: Message):
    """Show data prices."""
    response = await process_message(message.from_user.id, "Show me all data prices")
    await message.answer(response, parse_mode="Markdown")


@router.message(Command("fund"))
async def cmd_fund(message: Message):
    """Start wallet funding."""
    response = await process_message(message.from_user.id, "I want to fund my wallet")
    await message.answer(response, parse_mode="Markdown")


@router.message(Command("orders"))
async def cmd_orders(message: Message):
    """Show order history."""
    response = await process_message(message.from_user.id, "Show my order history")
    await message.answer(response, parse_mode="Markdown")


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
    await callback.message.edit_text(response, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "menu_balance")
async def cb_balance(callback: CallbackQuery):
    """Check wallet balance."""
    response = await process_message(callback.from_user.id, "Check my wallet balance")
    await callback.message.edit_text(
        response, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="menu_main")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "menu_fund")
async def cb_fund(callback: CallbackQuery):
    """Fund wallet prompt."""
    response = await process_message(callback.from_user.id, "I want to fund my wallet")
    await callback.message.edit_text(response, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "menu_orders")
async def cb_orders(callback: CallbackQuery):
    """Show order history."""
    response = await process_message(callback.from_user.id, "Show my recent orders")
    await callback.message.edit_text(
        response, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="menu_main")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "menu_history")
async def cb_history(callback: CallbackQuery):
    """Show wallet transaction history."""
    response = await process_message(callback.from_user.id, "Show my wallet history")
    await callback.message.edit_text(
        response, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="menu_main")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "menu_prices")
async def cb_prices(callback: CallbackQuery):
    """Show all data prices."""
    response = await process_message(callback.from_user.id, "Show me all data prices for all networks")
    await callback.message.edit_text(
        response, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="menu_main")]
        ])
    )
    await callback.answer()


# ─── General Message Handler (AI Conversation) ───────────────────────────────

@router.message(F.text)
async def handle_message(message: Message):
    """Handle all text messages — forward to Gemini AI."""
    user_id = message.from_user.id
    user_text = message.text.strip()

    if not user_text:
        return

    logger.info(f"Message from {user_id}: {user_text[:100]}")

    # Send typing indicator
    await message.bot.send_chat_action(message.chat.id, "typing")

    # Process through Gemini
    response = await process_message(user_id, user_text)

    # Send response (split if too long for Telegram's 4096 char limit)
    if len(response) <= 4096:
        await message.answer(response, parse_mode="Markdown")
    else:
        # Split into chunks
        chunks = [response[i:i+4000] for i in range(0, len(response), 4000)]
        for chunk in chunks:
            await message.answer(chunk, parse_mode="Markdown")
