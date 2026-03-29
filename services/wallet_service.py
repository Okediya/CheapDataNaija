"""
CheapDataNaija Bot — Wallet Service
Manages wallet funding, deductions, balance checks, and history.
"""

import logging
from database import (
    get_or_create_user, get_balance, update_balance,
    insert_transaction, get_transactions
)

logger = logging.getLogger(__name__)


class InsufficientFundsError(Exception):
    """Raised when wallet balance is too low for a debit."""
    pass


async def check_balance(telegram_id: int) -> float:
    """Get user's current wallet balance."""
    await get_or_create_user(telegram_id)
    balance = await get_balance(telegram_id)
    logger.info(f"Balance check for {telegram_id}: ₦{balance:,.2f}")
    return balance


async def fund_wallet(telegram_id: int, amount: float, reference: str = None) -> float:
    """Credit user's wallet. Returns new balance."""
    await get_or_create_user(telegram_id)

    new_balance = await update_balance(telegram_id, amount)
    await insert_transaction(
        user_id=telegram_id,
        tx_type="credit",
        amount=amount,
        description=f"Wallet funding — ₦{amount:,.2f}",
        reference=reference
    )
    logger.info(f"Funded wallet for {telegram_id}: +₦{amount:,.2f} → ₦{new_balance:,.2f}")
    return new_balance


async def deduct_wallet(telegram_id: int, amount: float, description: str = "") -> float:
    """Debit user's wallet. Returns new balance. Raises InsufficientFundsError if balance too low."""
    await get_or_create_user(telegram_id)

    current = await get_balance(telegram_id)
    if current < amount:
        raise InsufficientFundsError(
            f"Insufficient balance. You have ₦{current:,.2f} but need ₦{amount:,.2f}. "
            f"Please fund your wallet with at least ₦{amount - current:,.2f}."
        )

    new_balance = await update_balance(telegram_id, -amount)
    await insert_transaction(
        user_id=telegram_id,
        tx_type="debit",
        amount=amount,
        description=description or f"Purchase — ₦{amount:,.2f}",
        reference=None
    )
    logger.info(f"Debited wallet for {telegram_id}: -₦{amount:,.2f} → ₦{new_balance:,.2f}")
    return new_balance


async def get_wallet_history(telegram_id: int, limit: int = 10) -> list:
    """Get recent wallet transactions for the user."""
    await get_or_create_user(telegram_id)
    return await get_transactions(telegram_id, limit)
