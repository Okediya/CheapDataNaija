"""
CheapDataNaija Bot — Paystack Payment Service
Handles payment initialization, verification, and webhook processing.
"""

import hashlib
import hmac
import json
import httpx
import logging
from config import PAYSTACK_SECRET_KEY, PAYSTACK_PUBLIC_KEY

logger = logging.getLogger(__name__)

PAYSTACK_BASE_URL = "https://api.paystack.co"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }


async def initialize_transaction(email: str, amount_naira: float,
                                  telegram_id: int, callback_url: str = None) -> dict:
    """Initialize a Paystack transaction for wallet funding.
    
    Args:
        email: Customer email (can use telegram_id@cheapdatanaija.bot as fallback).
        amount_naira: Amount in Naira (will be converted to kobo).
        telegram_id: Telegram user ID for metadata tracking.
        callback_url: Optional callback URL after payment.
    
    Returns:
        Dict with authorization_url, reference, and access_code.
    """
    amount_kobo = int(amount_naira * 100)

    payload = {
        "email": email,
        "amount": amount_kobo,
        "metadata": {
            "telegram_id": telegram_id,
            "purpose": "wallet_funding",
        },
        "channels": ["card", "bank", "ussd", "bank_transfer"],
    }

    if callback_url:
        payload["callback_url"] = callback_url

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{PAYSTACK_BASE_URL}/transaction/initialize",
                json=payload,
                headers=_headers()
            )
            data = response.json()

            if data.get("status"):
                tx_data = data["data"]
                logger.info(f"Paystack transaction initialized: {tx_data['reference']}")
                return {
                    "success": True,
                    "authorization_url": tx_data["authorization_url"],
                    "reference": tx_data["reference"],
                    "access_code": tx_data["access_code"],
                }
            else:
                logger.error(f"Paystack init failed: {data.get('message')}")
                return {
                    "success": False,
                    "message": data.get("message", "Could not initialize payment."),
                }
    except Exception as e:
        logger.error(f"Paystack init error: {e}")
        return {"success": False, "message": f"Payment service error: {str(e)}"}


async def verify_transaction(reference: str) -> dict:
    """Verify a Paystack transaction by reference.
    
    Returns:
        Dict with success status, amount (in Naira), and metadata.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}",
                headers=_headers()
            )
            data = response.json()

            if data.get("status") and data["data"]["status"] == "success":
                tx_data = data["data"]
                amount_naira = tx_data["amount"] / 100
                metadata = tx_data.get("metadata", {})
                logger.info(f"Paystack verified: {reference} — ₦{amount_naira:,.2f}")
                return {
                    "success": True,
                    "amount": amount_naira,
                    "reference": reference,
                    "telegram_id": metadata.get("telegram_id"),
                    "metadata": metadata,
                }
            else:
                return {
                    "success": False,
                    "message": "Transaction verification failed or payment was not successful.",
                }
    except Exception as e:
        logger.error(f"Paystack verify error: {e}")
        return {"success": False, "message": f"Verification error: {str(e)}"}


def validate_webhook_signature(payload_body: bytes, signature: str) -> bool:
    """Validate Paystack webhook HMAC signature.
    
    Args:
        payload_body: Raw request body bytes.
        signature: x-paystack-signature header value.
    
    Returns:
        True if signature is valid.
    """
    expected = hmac.HMAC(
        PAYSTACK_SECRET_KEY.encode("utf-8"),
        payload_body,
        hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


async def process_webhook_event(payload: dict) -> dict:
    """Process a Paystack webhook event.
    
    Args:
        payload: Parsed JSON payload from Paystack webhook.
    
    Returns:
        Dict with event type, amount, telegram_id, and reference if applicable.
    """
    event = payload.get("event", "")
    data = payload.get("data", {})

    if event == "charge.success":
        amount_naira = data.get("amount", 0) / 100
        metadata = data.get("metadata", {})
        reference = data.get("reference", "")
        telegram_id = metadata.get("telegram_id")

        logger.info(f"Webhook charge.success: ₦{amount_naira:,.2f} for user {telegram_id}")

        return {
            "event": "charge.success",
            "amount": amount_naira,
            "telegram_id": telegram_id,
            "reference": reference,
            "success": True,
        }

    logger.info(f"Ignoring webhook event: {event}")
    return {"event": event, "success": False, "message": "Event not handled."}
