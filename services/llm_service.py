"""
CheapDataNaija Bot — LLM Service (Groq API)
Conversational AI engine with tool-calling for data purchases, wallet management, etc.
Uses Groq's Llama 3.3.
"""

import json
import logging
from groq import AsyncGroq
from config import GROQ_API_KEY
from services import wallet_service, smedata_service, paystack_service
from database import get_orders, get_or_create_user

logger = logging.getLogger(__name__)

# Configure Groq client
client = AsyncGroq(api_key=GROQ_API_KEY)
MODEL_NAME = "llama-3.3-70b-versatile"

# ─── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are CheapDataNaija Bot — a friendly, professional AI assistant that helps users buy affordable MTN, Airtel, and Glo data bundles instantly.

IMPORTANT RULES:
1. Always use clean, professional, and clear standard English. No slang, no Pidgin.
2. Be friendly, polite, concise, and helpful.
3. When a user wants to buy data, ALWAYS follow this flow:
   a. Identify the network, data size, and phone number.
   b. If any detail is missing, ask for it politely.
   c. Once you have all details, call get_data_prices to confirm the price.
   d. Call check_wallet_balance to show the user their balance alongside the price.
   e. Summarize the order: network, size, phone, price, current balance.
   f. Ask the user to confirm with "Yes" before purchasing.
   g. On confirmation, call buy_data_bundle to complete the purchase.
4. If the user's balance is insufficient, suggest funding their wallet. Call generate_funding_link with the needed amount.
5. For wallet-related queries, use check_wallet_balance, get_wallet_history, or generate_funding_link as appropriate.
6. For order history, use get_order_history.
7. Always show prices in Naira with the ₦ symbol.
8. Phone numbers should be 11 digits starting with 0 (Nigerian format).
9. If the user says "yes", "confirm", "proceed", "go ahead" and there is a pending purchase context, proceed with the purchase.
10. Available networks: MTN, Airtel, Glo. Do not offer 9mobile.

PURCHASE CONFIRMATION FORMAT:
📋 Order Summary:
• Network: [NETWORK]
• Data: [SIZE]
• Phone: [PHONE]
• Price: ₦[PRICE]
• Wallet Balance: ₦[BALANCE]

Reply "Yes" to confirm this purchase.

SUCCESSFUL PURCHASE FORMAT:
✅ Purchase Successful!
• [SIZE] [NETWORK] data sent to [PHONE]
• Amount Charged: ₦[PRICE]
• Remaining Balance: ₦[NEW_BALANCE]

Thank you for choosing CheapDataNaija!
"""

# ─── Tool Declarations (Groq / OpenAI Format) ────────────────────────────────

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_data_prices",
            "description": "Get available data bundle prices. Optionally filter by network name (MTN, AIRTEL, GLO). Returns all prices if no network specified.",
            "parameters": {
                "type": "object",
                "properties": {
                    "network": {
                        "type": "string",
                        "description": "Network name to filter by: MTN, AIRTEL, or GLO. Leave empty for all networks."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_wallet_balance",
            "description": "Check the user's current wallet balance in Naira.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buy_data_bundle",
            "description": "Purchase a data bundle for a phone number. Deducts from wallet and calls the VTU provider. Only call this after the user has explicitly confirmed the purchase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "network": {
                        "type": "string",
                        "description": "Network name: MTN, AIRTEL, or GLO"
                    },
                    "size": {
                        "type": "string",
                        "description": "Data size: 1GB, 2GB, 3GB, 5GB, or 10GB"
                    },
                    "phone": {
                        "type": "string",
                        "description": "Recipient phone number (11 digits, starting with 0)"
                    }
                },
                "required": ["network", "size", "phone"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_funding_link",
            "description": "Generate a Paystack payment link for the user to fund their wallet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "number",
                        "description": "Amount in Naira to fund the wallet with"
                    }
                },
                "required": ["amount"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_order_history",
            "description": "Get the user's recent data purchase history.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_wallet_history",
            "description": "Get the user's recent wallet transaction history (credits and debits).",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]

# ─── Tool Execution ──────────────────────────────────────────────────────────

async def execute_tool(function_name: str, args: dict, telegram_id: int) -> str:
    """Execute a tool function and return the result as a JSON string."""
    try:
        if function_name == "get_data_prices":
            network = args.get("network", None)
            prices = smedata_service.get_prices(network)
            return json.dumps(prices, indent=2)

        elif function_name == "check_wallet_balance":
            balance = await wallet_service.check_balance(telegram_id)
            return json.dumps({"balance": balance, "formatted": f"₦{balance:,.2f}"})

        elif function_name == "buy_data_bundle":
            network = args.get("network", "").upper()
            size = args.get("size", "").upper()
            phone = args.get("phone", "")

            # Get price
            price = smedata_service.get_price(network, size)
            if price is None:
                return json.dumps({"success": False, "message": f"No {size} plan available for {network}."})

            # Deduct wallet
            try:
                new_balance = await wallet_service.deduct_wallet(
                    telegram_id, price,
                    f"{size} {network} data for {phone}"
                )
            except wallet_service.InsufficientFundsError as e:
                return json.dumps({"success": False, "message": str(e)})

            # Call SMEDATA API
            from database import insert_order, update_order_status
            order_id = await insert_order(
                user_id=telegram_id, network=network, size=size,
                phone=phone, amount=price, status="processing"
            )

            result = await smedata_service.buy_data(network, size, phone)

            if result["success"]:
                await update_order_status(order_id, "completed", json.dumps(result.get("details", {})))
                return json.dumps({
                    "success": True,
                    "message": result["message"],
                    "amount_charged": price,
                    "new_balance": new_balance,
                    "order_id": order_id,
                })
            else:
                # Refund on failure
                await wallet_service.fund_wallet(telegram_id, price, f"refund_order_{order_id}")
                await update_order_status(order_id, "failed", json.dumps(result))
                return json.dumps({
                    "success": False,
                    "message": f"Purchase failed: {result['message']}. Your wallet has been refunded ₦{price:,.2f}.",
                    "refunded": True,
                })

        elif function_name == "generate_funding_link":
            amount = float(args.get("amount", 0))
            email = f"{telegram_id}@cheapdatanaija.bot"
            result = await paystack_service.initialize_transaction(
                email=email, amount_naira=amount, telegram_id=telegram_id
            )
            if result["success"]:
                return json.dumps({
                    "success": True,
                    "payment_url": result["authorization_url"],
                    "reference": result["reference"],
                    "amount": amount,
                })
            else:
                return json.dumps({"success": False, "message": result["message"]})

        elif function_name == "get_order_history":
            orders = await get_orders(telegram_id, limit=10)
            if not orders:
                return json.dumps({"orders": [], "message": "You have no orders yet."})
            return json.dumps({"orders": orders})

        elif function_name == "get_wallet_history":
            transactions = await wallet_service.get_wallet_history(telegram_id, limit=10)
            if not transactions:
                return json.dumps({"transactions": [], "message": "No wallet transactions yet."})
            return json.dumps({"transactions": transactions})

        else:
            return json.dumps({"error": f"Unknown tool: {function_name}"})

    except Exception as e:
        logger.error(f"Tool execution error ({function_name}): {e}", exc_info=True)
        return json.dumps({"error": f"An error occurred: {str(e)}"})


# ─── Conversation Management ─────────────────────────────────────────────────

# In-memory conversation history per user (limited to last N turns)
_conversations: dict[int, list] = {}
MAX_HISTORY = 20

def _get_history(telegram_id: int) -> list:
    if telegram_id not in _conversations:
        _conversations[telegram_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    return _conversations[telegram_id]

def _trim_history(telegram_id: int):
    history = _conversations.get(telegram_id, [])
    if len(history) > MAX_HISTORY * 2 + 1:
        trim_index = len(history) - (MAX_HISTORY * 2)
        # Ensure we always start with a user message to prevent API errors
        while trim_index < len(history) and history[trim_index].get("role") != "user":
            trim_index += 1
        _conversations[telegram_id] = [history[0]] + history[trim_index:]


# ─── Main Processing ─────────────────────────────────────────────────────────

async def process_message(telegram_id: int, user_text: str) -> str:
    """Process a user message through Groq with tool-calling support.
    
    Args:
        telegram_id: Telegram user ID.
        user_text: The user's message text.
    
    Returns:
        The bot's text response to send back to the user.
    """
    # Ensure user exists in DB
    await get_or_create_user(telegram_id)

    history = _get_history(telegram_id)
    history.append({"role": "user", "content": user_text})

    try:
        # Loop for handling multi-step tool calls
        while True:
            response = await client.chat.completions.create(
                model=MODEL_NAME,
                messages=history,
                tools=tools,
                tool_choice="auto"
            )
            
            response_msg = response.choices[0].message

            # Handle case where both text and tool calls might be present
            if getattr(response_msg, "tool_calls", None):
                # We append the assistant's request so Groq remembers its own tool calls
                history.append({
                    "role": "assistant",
                    "content": response_msg.content,
                    "tool_calls": [tool_call.model_dump() for tool_call in response_msg.tool_calls]
                })
                
                # Execute all tools in parallel (or sequential)
                for tool_call in response_msg.tool_calls:
                    fn_name = tool_call.function.name
                    try:
                        fn_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        fn_args = {}
                        
                    logger.info(f"Groq tool call: {fn_name}({fn_args}) for user {telegram_id}")

                    # Execute the tool
                    result_str = await execute_tool(fn_name, fn_args, telegram_id)
                    
                    # Provide result back to LLM
                    history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.function.name,
                        "content": result_str
                    })
                
                # After appending all tool results, loop around to send the history again
                continue

            else:
                # No tool calls; standard text response
                reply_text = response_msg.content or ""
                history.append({"role": "assistant", "content": reply_text})
                break

        _trim_history(telegram_id)

        return reply_text.strip() if reply_text.strip() else "I'm sorry, I could not process that request. Please try again."

    except Exception as e:
        # If an error occurs, pop the user message to prevent getting stuck
        if history and history[-1].get("role") == "user":
            history.pop()
        logger.error(f"Groq processing error for user {telegram_id}: {e}", exc_info=True)
        return (
            "I apologize, but I encountered an error processing your request. "
            "Please try again or use /menu for quick options."
        )
