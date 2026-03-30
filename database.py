"""
CheapDataNaija Bot — Database Layer
SQLite database with aiosqlite for async operations.
"""

import math
import aiosqlite
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from config import DATABASE_PATH

logger = logging.getLogger(__name__)

_db_path: str = DATABASE_PATH

# ─── Profit Markup ────────────────────────────────────────────────────────────
PROFIT_MARGIN = 0.10  # 10% markup


def calculate_selling_price(cost_price: float) -> float:
    """Calculate selling price with 10% markup, rounded up to nearest whole number."""
    return math.ceil(cost_price * (1 + PROFIT_MARGIN))


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
                cost_price REAL NOT NULL DEFAULT 0.0,
                profit REAL NOT NULL DEFAULT 0.0,
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

            CREATE TABLE IF NOT EXISTS data_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                network TEXT NOT NULL,
                network_id TEXT NOT NULL,
                size TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                cost_price REAL NOT NULL,
                price REAL NOT NULL,
                UNIQUE(network, size)
            );

            CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
            CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id);
            CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);
        """)
        await db.commit()

        # Migrate existing tables: add cost_price/profit columns if missing
        try:
            await db.execute("SELECT cost_price FROM orders LIMIT 1")
        except Exception:
            logger.info("Migrating orders table: adding cost_price and profit columns...")
            await db.execute("ALTER TABLE orders ADD COLUMN cost_price REAL NOT NULL DEFAULT 0.0")
            await db.execute("ALTER TABLE orders ADD COLUMN profit REAL NOT NULL DEFAULT 0.0")
            await db.commit()

        try:
            await db.execute("SELECT cost_price FROM data_plans LIMIT 1")
        except Exception:
            logger.info("Migrating data_plans table: adding cost_price column...")
            await db.execute("ALTER TABLE data_plans ADD COLUMN cost_price REAL NOT NULL DEFAULT 0.0")
            # Copy current prices as cost_price, then update price with markup
            await db.execute("UPDATE data_plans SET cost_price = price")
            await db.execute(f"UPDATE data_plans SET price = CAST(cost_price * {1 + PROFIT_MARGIN} + 0.99 AS INTEGER)")
            await db.commit()

        # Bootstrap plans ONLY if table is empty
        cursor = await db.execute("SELECT COUNT(*) FROM data_plans")
        count = (await cursor.fetchone())[0]
        if count == 0:
            logger.info("Bootstrapping data_plans table with SMEDATA prices + 10% markup...")
            # Cost prices from SMEDATA.NG (reseller prices)
            default_plans = [
                # (network, network_id, size, plan_id, cost_price)
                # MTN SME Data
                ("MTN", "1", "1GB", "1gb", 250),
                ("MTN", "1", "2GB", "2gb", 500),
                ("MTN", "1", "3GB", "3gb", 750),
                ("MTN", "1", "5GB", "5gb", 1200),
                ("MTN", "1", "10GB", "10gb1m", 2400),
                # Airtel CG Data
                ("AIRTEL", "2", "1GB", "1gb1w", 250),
                ("AIRTEL", "2", "2GB", "2gb1m", 500),
                ("AIRTEL", "2", "3GB", "3gb1m", 750),
                ("AIRTEL", "2", "5GB", "5gb1m", 1200),
                # GLO CG Data
                ("GLO", "3", "1GB", "1GB", 240),
                ("GLO", "3", "2GB", "2GB", 480),
                ("GLO", "3", "3GB", "3GB", 720),
                ("GLO", "3", "5GB", "5GB", 1150),
            ]
            for network, network_id, size, plan_id, cost_price in default_plans:
                selling_price = calculate_selling_price(cost_price)
                await db.execute(
                    "INSERT INTO data_plans (network, network_id, size, plan_id, cost_price, price) VALUES (?, ?, ?, ?, ?, ?)",
                    (network, network_id, size, plan_id, cost_price, selling_price)
                )
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
    cost_price: float = 0.0,
    profit: float = 0.0,
    status: str = "pending",
    api_response: Optional[str] = None,
) -> int:
    """Insert a new order. Returns the order ID."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO orders (user_id, network, size, phone, amount, cost_price, profit, status, api_response)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, network, size, phone, amount, cost_price, profit, status, api_response)
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

# ─── Data Plans Management ───────────────────────────────────────────────────

async def get_all_plans() -> List[Dict[str, Any]]:
    """Get all available data plans from the database."""
    db = await _get_db()
    try:
        cursor = await db.execute("SELECT * FROM data_plans ORDER BY network ASC, price ASC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_plan(network: str, size: str) -> Optional[Dict[str, Any]]:
    """Get a specific data plan by network and size."""
    db = await _get_db()
    network = network.upper().strip()
    size = size.upper().strip().replace(" ", "")
    try:
        cursor = await db.execute(
            "SELECT * FROM data_plans WHERE network = ? AND size = ?",
            (network, size)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def add_or_update_plan(network: str, network_id: str, size: str, plan_id: str, cost_price: float) -> None:
    """Add a new data plan or update an existing one. Price is auto-calculated with 10% markup."""
    network = network.upper().strip()
    size = size.upper().strip().replace(" ", "")
    selling_price = calculate_selling_price(cost_price)
    db = await _get_db()
    try:
        await db.execute(
            """INSERT INTO data_plans (network, network_id, size, plan_id, cost_price, price)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(network, size) DO UPDATE SET
               network_id=excluded.network_id,
               plan_id=excluded.plan_id,
               cost_price=excluded.cost_price,
               price=excluded.price""",
            (network, network_id, size, plan_id, cost_price, selling_price)
        )
        await db.commit()
    finally:
        await db.close()


async def delete_plan(network: str, size: str) -> bool:
    """Delete a plan by network and size. Returns True if deleted, False if not found."""
    network = network.upper().strip()
    size = size.upper().strip().replace(" ", "")
    db = await _get_db()
    try:
        cursor = await db.execute(
            "DELETE FROM data_plans WHERE network = ? AND size = ?",
            (network, size)
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


# ─── Profit / Gains Analytics ────────────────────────────────────────────────

async def get_profit_stats() -> Dict[str, Any]:
    """Get profit statistics: today, this week, this month, this year, and all-time.
    Only counts completed orders.
    """
    db = await _get_db()
    try:
        stats = {}

        # Today
        cursor = await db.execute(
            """SELECT COALESCE(SUM(profit), 0) as total_profit,
                      COALESCE(SUM(amount), 0) as total_revenue,
                      COALESCE(SUM(cost_price), 0) as total_cost,
                      COUNT(*) as order_count
               FROM orders
               WHERE status = 'completed'
               AND date(created_at) = date('now')"""
        )
        row = await cursor.fetchone()
        stats["today"] = dict(row)

        # This week (last 7 days)
        cursor = await db.execute(
            """SELECT COALESCE(SUM(profit), 0) as total_profit,
                      COALESCE(SUM(amount), 0) as total_revenue,
                      COALESCE(SUM(cost_price), 0) as total_cost,
                      COUNT(*) as order_count
               FROM orders
               WHERE status = 'completed'
               AND created_at >= datetime('now', '-7 days')"""
        )
        row = await cursor.fetchone()
        stats["week"] = dict(row)

        # This month
        cursor = await db.execute(
            """SELECT COALESCE(SUM(profit), 0) as total_profit,
                      COALESCE(SUM(amount), 0) as total_revenue,
                      COALESCE(SUM(cost_price), 0) as total_cost,
                      COUNT(*) as order_count
               FROM orders
               WHERE status = 'completed'
               AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')"""
        )
        row = await cursor.fetchone()
        stats["month"] = dict(row)

        # This year
        cursor = await db.execute(
            """SELECT COALESCE(SUM(profit), 0) as total_profit,
                      COALESCE(SUM(amount), 0) as total_revenue,
                      COALESCE(SUM(cost_price), 0) as total_cost,
                      COUNT(*) as order_count
               FROM orders
               WHERE status = 'completed'
               AND strftime('%Y', created_at) = strftime('%Y', 'now')"""
        )
        row = await cursor.fetchone()
        stats["year"] = dict(row)

        # All time
        cursor = await db.execute(
            """SELECT COALESCE(SUM(profit), 0) as total_profit,
                      COALESCE(SUM(amount), 0) as total_revenue,
                      COALESCE(SUM(cost_price), 0) as total_cost,
                      COUNT(*) as order_count
               FROM orders
               WHERE status = 'completed'"""
        )
        row = await cursor.fetchone()
        stats["all_time"] = dict(row)

        # Total users
        cursor = await db.execute("SELECT COUNT(*) as count FROM users")
        row = await cursor.fetchone()
        stats["total_users"] = row["count"]

        return stats
    finally:
        await db.close()
