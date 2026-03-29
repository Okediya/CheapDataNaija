"""
CheapDataNaija Bot — Database Layer
SQLite database with aiosqlite for async operations.
"""

import aiosqlite
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from config import DATABASE_PATH

logger = logging.getLogger(__name__)

_db_path: str = DATABASE_PATH


async def _get_db():
    """Open a database connection with row factory and pragmas."""
    db = await aiosqlite.connect(_db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db() -> None:
    """Initialize database tables."""
    db = await _get_db()
    try:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                wallet_balance REAL NOT NULL DEFAULT 0.0,
                phone TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                network TEXT NOT NULL,
                size TEXT NOT NULL,
                phone TEXT NOT NULL,
                amount REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                api_response TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('credit', 'debit')),
                amount REAL NOT NULL,
                description TEXT,
                reference TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            );

            CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
            CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id);
        """)
        await db.commit()
        logger.info("Database initialized successfully.")
    finally:
        await db.close()


async def get_or_create_user(telegram_id: int) -> Dict[str, Any]:
    """Get existing user or create a new one. Returns user dict."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT telegram_id, wallet_balance, phone, created_at FROM users WHERE telegram_id = ?",
            (telegram_id,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)

        await db.execute(
            "INSERT INTO users (telegram_id) VALUES (?)",
            (telegram_id,)
        )
        await db.commit()
        return {
            "telegram_id": telegram_id,
            "wallet_balance": 0.0,
            "phone": None,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    finally:
        await db.close()


async def get_balance(telegram_id: int) -> float:
    """Get wallet balance for a user."""
    user = await get_or_create_user(telegram_id)
    return float(user["wallet_balance"])


async def update_balance(telegram_id: int, amount: float) -> float:
    """Atomically update user balance. amount can be positive (credit) or negative (debit).
    Returns the new balance. Raises ValueError if debit would go below zero.
    """
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT wallet_balance FROM users WHERE telegram_id = ?",
            (telegram_id,)
        )
        row = await cursor.fetchone()
        if not row:
            await db.close()
            await get_or_create_user(telegram_id)
            db = await _get_db()
            current = 0.0
        else:
            current = float(row["wallet_balance"])

        new_balance = current + amount
        if new_balance < 0:
            raise ValueError(
                f"Insufficient balance. Current: ₦{current:,.2f}, "
                f"Attempted debit: ₦{abs(amount):,.2f}"
            )

        await db.execute(
            "UPDATE users SET wallet_balance = ? WHERE telegram_id = ?",
            (new_balance, telegram_id)
        )
        await db.commit()
        return new_balance
    finally:
        await db.close()


async def insert_order(
    user_id: int,
    network: str,
    size: str,
    phone: str,
    amount: float,
    status: str = "pending",
    api_response: Optional[str] = None,
) -> int:
    """Insert a new order. Returns the order ID."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO orders (user_id, network, size, phone, amount, status, api_response)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, network, size, phone, amount, status, api_response)
        )
        await db.commit()
        order_id = cursor.lastrowid
        return order_id if order_id is not None else 0
    finally:
        await db.close()


async def update_order_status(
    order_id: int,
    status: str,
    api_response: Optional[str] = None,
) -> None:
    """Update the status of an order."""
    db = await _get_db()
    try:
        if api_response:
            await db.execute(
                "UPDATE orders SET status = ?, api_response = ? WHERE id = ?",
                (status, api_response, order_id)
            )
        else:
            await db.execute(
                "UPDATE orders SET status = ? WHERE id = ?",
                (status, order_id)
            )
        await db.commit()
    finally:
        await db.close()


async def get_orders(telegram_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent orders for a user."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            """SELECT id, network, size, phone, amount, status, created_at
               FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT ?""",
            (telegram_id, limit)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def insert_transaction(
    user_id: int,
    tx_type: str,
    amount: float,
    description: str,
    reference: Optional[str] = None,
) -> int:
    """Insert a wallet transaction record. Returns transaction ID."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO transactions (user_id, type, amount, description, reference)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, tx_type, amount, description, reference)
        )
        await db.commit()
        tx_id = cursor.lastrowid
        return tx_id if tx_id is not None else 0
    finally:
        await db.close()


async def get_transactions(telegram_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent wallet transactions."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            """SELECT id, type, amount, description, reference, created_at
               FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?""",
            (telegram_id, limit)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()
