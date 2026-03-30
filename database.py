"""
CheapDataNaija Bot — Database Layer
PostgreSQL database with asyncpg for async operations.
Persistent storage that survives Render redeploys.
"""

import math
import asyncpg
import logging
from typing import Any, Dict, List, Optional
from config import DATABASE_URL

logger = logging.getLogger(__name__)

# ─── Profit Markup ────────────────────────────────────────────────────────────
PROFIT_MARGIN = 0.02  # 2% markup

# ─── Connection Pool ─────────────────────────────────────────────────────────
_pool: Optional[asyncpg.Pool] = None


def calculate_selling_price(cost_price: float) -> float:
    """Calculate selling price with 2% markup, rounded up to nearest whole number."""
    return math.ceil(cost_price * (1 + PROFIT_MARGIN))


async def _get_pool() -> asyncpg.Pool:
    """Get or create the connection pool."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return _pool


async def close_pool() -> None:
    """Close the connection pool (call on shutdown)."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def init_db() -> None:
    """Initialize database tables."""
    pool = await _get_pool()

    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id BIGINT PRIMARY KEY,
                wallet_balance DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                phone TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(telegram_id),
                network TEXT NOT NULL,
                size TEXT NOT NULL,
                phone TEXT NOT NULL,
                amount DOUBLE PRECISION NOT NULL,
                cost_price DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                profit DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                status TEXT NOT NULL DEFAULT 'pending',
                api_response TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(telegram_id),
                type TEXT NOT NULL CHECK(type IN ('credit', 'debit')),
                amount DOUBLE PRECISION NOT NULL,
                description TEXT,
                reference TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS data_plans (
                id SERIAL PRIMARY KEY,
                network TEXT NOT NULL,
                network_id TEXT NOT NULL,
                size TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                cost_price DOUBLE PRECISION NOT NULL,
                price DOUBLE PRECISION NOT NULL,
                duration TEXT NOT NULL DEFAULT '30 days',
                UNIQUE(network, size)
            );
        """)

        # Create indexes if they don't exist
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);")

        # Bootstrap plans ONLY if table is empty
        count = await conn.fetchval("SELECT COUNT(*) FROM data_plans")
        if count == 0:
            logger.info("Bootstrapping data_plans table with SMEDATA prices + 2% markup...")
            default_plans = [
                # ─── MTN Data Share (SME) — 30 days ──────────────────
                ("MTN", "1", "1GB-SME-MONTHLY", "1gb", 600, "30 days"),
                ("MTN", "1", "2GB-SME-MONTHLY", "2gb", 1200, "30 days"),
                ("MTN", "1", "3GB-SME-MONTHLY", "3gb", 1800, "30 days"),
                ("MTN", "1", "5GB-SME-MONTHLY", "5gb", 3000, "30 days"),
                # ─── MTN Direct Data ──────────────────────────────────
                ("MTN", "1", "230MB-DAILY", "230mb1d", 200, "1 day"),
                ("MTN", "1", "1GB-DAILY", "1gb1d", 486, "1 day"),
                ("MTN", "1", "1.5GB-2DAYS", "1.5gb2d", 585, "2 days"),
                ("MTN", "1", "1GB-WEEKLY", "1gb1w", 785, "7 days"),
                ("MTN", "1", "2.5GB-DAILY", "2.5gb1d", 600, "1 day"),
                ("MTN", "1", "2.5GB-2DAYS", "2.5gb2d", 885, "2 days"),
                ("MTN", "1", "1.5GB-WEEKLY", "1.5gb1w", 980, "7 days"),
                ("MTN", "1", "2GB-MONTHLY", "2gb1m", 1465, "30 days"),
                ("MTN", "1", "2.7GB-MONTHLY", "2.7gb1m", 1950, "30 days"),
                ("MTN", "1", "6GB-WEEKLY", "6gb1w", 2430, "7 days"),
                ("MTN", "1", "3.5GB-MONTHLY", "3.5gb1m", 2450, "30 days"),
                ("MTN", "1", "7GB-MONTHLY", "7gb1m", 3420, "30 days"),
                ("MTN", "1", "10GB-MONTHLY", "10gb1m", 4400, "30 days"),
                ("MTN", "1", "12.5GB-MONTHLY", "12.5gb1m", 5400, "30 days"),
                ("MTN", "1", "16.5GB-MONTHLY", "16.5gb1m", 6350, "30 days"),
                ("MTN", "1", "20GB-MONTHLY", "20gb1m", 7350, "30 days"),
                ("MTN", "1", "25GB-MONTHLY", "25gb1m", 8800, "30 days"),
                # ─── Airtel Direct Data ───────────────────────────────
                ("AIRTEL", "2", "300MB-2DAYS", "300mb2d", 297, "2 days"),
                ("AIRTEL", "2", "500MB-WEEKLY", "500mb1w", 490, "7 days"),
                ("AIRTEL", "2", "1.5GB-2DAYS", "1.5gb2d", 590, "2 days"),
                ("AIRTEL", "2", "1GB-WEEKLY", "1gb1w", 780, "7 days"),
                ("AIRTEL", "2", "1.5GB-WEEKLY", "1.5gb1w", 980, "7 days"),
                ("AIRTEL", "2", "3.5GB-WEEKLY", "3.5gb1w", 1470, "7 days"),
                ("AIRTEL", "2", "2GB-MONTHLY", "2gb1m", 1480, "30 days"),
                ("AIRTEL", "2", "3GB-MONTHLY", "3gb1m", 1970, "30 days"),
                ("AIRTEL", "2", "6GB-WEEKLY", "6gb1w", 2450, "7 days"),
                ("AIRTEL", "2", "4GB-MONTHLY", "4gb1m", 2470, "30 days"),
                ("AIRTEL", "2", "10GB-WEEKLY", "10gb1w", 2950, "7 days"),
                ("AIRTEL", "2", "8GB-MONTHLY", "8gb1m", 2970, "30 days"),
                ("AIRTEL", "2", "10GB-MONTHLY", "10gb1m", 3930, "30 days"),
                ("AIRTEL", "2", "15GB-WEEKLY", "15gb1w", 4870, "7 days"),
                ("AIRTEL", "2", "13GB-MONTHLY", "13gb1m", 4900, "30 days"),
                ("AIRTEL", "2", "18GB-MONTHLY", "18gb1m", 5880, "30 days"),
                ("AIRTEL", "2", "25GB-MONTHLY", "25gb1m", 7830, "30 days"),
                ("AIRTEL", "2", "35GB-MONTHLY", "35gb1m", 9770, "30 days"),
                # ─── GLO CG Data — 30 days ───────────────────────────
                ("GLO", "3", "500MB-MONTHLY", "500MB", 280, "30 days"),
                ("GLO", "3", "1GB-MONTHLY", "1GB", 480, "30 days"),
                ("GLO", "3", "2GB-MONTHLY", "2GB", 960, "30 days"),
                ("GLO", "3", "3GB-MONTHLY", "3GB", 1440, "30 days"),
                ("GLO", "3", "5GB-MONTHLY", "5GB", 2400, "30 days"),
                ("GLO", "3", "10GB-MONTHLY", "10GB", 4800, "30 days"),
            ]
            for network, network_id, size, plan_id, cost_price, duration in default_plans:
                selling_price = calculate_selling_price(cost_price)
                await conn.execute(
                    """INSERT INTO data_plans (network, network_id, size, plan_id, cost_price, price, duration)
                       VALUES ($1, $2, $3, $4, $5, $6, $7)
                       ON CONFLICT (network, size) DO NOTHING""",
                    network, network_id, size, plan_id, cost_price, float(selling_price), duration
                )

    logger.info("Database initialized successfully.")


async def get_or_create_user(telegram_id: int) -> Dict[str, Any]:
    """Get existing user or create a new one. Returns user dict."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT telegram_id, wallet_balance, phone, created_at FROM users WHERE telegram_id = $1",
            telegram_id
        )
        if row:
            return dict(row)

        await conn.execute(
            "INSERT INTO users (telegram_id) VALUES ($1) ON CONFLICT DO NOTHING",
            telegram_id
        )
        return {
            "telegram_id": telegram_id,
            "wallet_balance": 0.0,
            "phone": None,
            "created_at": None
        }


async def get_balance(telegram_id: int) -> float:
    """Get wallet balance for a user."""
    user = await get_or_create_user(telegram_id)
    return float(user["wallet_balance"])


async def update_balance(telegram_id: int, amount: float) -> float:
    """Atomically update user balance. amount can be positive (credit) or negative (debit).
    Returns the new balance. Raises ValueError if debit would go below zero.
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT wallet_balance FROM users WHERE telegram_id = $1",
            telegram_id
        )
        if not row:
            await get_or_create_user(telegram_id)
            current = 0.0
        else:
            current = float(row["wallet_balance"])

        new_balance = current + amount
        if new_balance < 0:
            raise ValueError(
                f"Insufficient balance. Current: ₦{current:,.2f}, "
                f"Attempted debit: ₦{abs(amount):,.2f}"
            )

        await conn.execute(
            "UPDATE users SET wallet_balance = $1 WHERE telegram_id = $2",
            new_balance, telegram_id
        )
        return new_balance


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
    pool = await _get_pool()
    async with pool.acquire() as conn:
        order_id = await conn.fetchval(
            """INSERT INTO orders (user_id, network, size, phone, amount, cost_price, profit, status, api_response)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id""",
            user_id, network, size, phone, amount, cost_price, profit, status, api_response
        )
        return order_id if order_id is not None else 0


async def update_order_status(
    order_id: int,
    status: str,
    api_response: Optional[str] = None,
) -> None:
    """Update the status of an order."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        if api_response:
            await conn.execute(
                "UPDATE orders SET status = $1, api_response = $2 WHERE id = $3",
                status, api_response, order_id
            )
        else:
            await conn.execute(
                "UPDATE orders SET status = $1 WHERE id = $2",
                status, order_id
            )


async def get_orders(telegram_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent orders for a user."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, network, size, phone, amount, status, created_at
               FROM orders WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2""",
            telegram_id, limit
        )
        return [dict(r) for r in rows]


async def insert_transaction(
    user_id: int,
    tx_type: str,
    amount: float,
    description: str,
    reference: Optional[str] = None,
) -> int:
    """Insert a wallet transaction record. Returns transaction ID."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        tx_id = await conn.fetchval(
            """INSERT INTO transactions (user_id, type, amount, description, reference)
               VALUES ($1, $2, $3, $4, $5) RETURNING id""",
            user_id, tx_type, amount, description, reference
        )
        return tx_id if tx_id is not None else 0


async def get_transactions(telegram_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent wallet transactions."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, type, amount, description, reference, created_at
               FROM transactions WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2""",
            telegram_id, limit
        )
        return [dict(r) for r in rows]


# ─── Data Plans Management ───────────────────────────────────────────────────

async def get_all_plans() -> List[Dict[str, Any]]:
    """Get all available data plans from the database."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM data_plans ORDER BY network ASC, price ASC")
        return [dict(r) for r in rows]


async def get_plan(network: str, size: str) -> Optional[Dict[str, Any]]:
    """Get a specific data plan by network and size."""
    pool = await _get_pool()
    network = network.upper().strip()
    size = size.upper().strip().replace(" ", "")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM data_plans WHERE network = $1 AND size = $2",
            network, size
        )
        return dict(row) if row else None


async def add_or_update_plan(network: str, network_id: str, size: str, plan_id: str, cost_price: float, duration: str = "30 days") -> None:
    """Add a new data plan or update an existing one. Price is auto-calculated with 2% markup."""
    network = network.upper().strip()
    size = size.upper().strip().replace(" ", "")
    selling_price = calculate_selling_price(cost_price)
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO data_plans (network, network_id, size, plan_id, cost_price, price, duration)
               VALUES ($1, $2, $3, $4, $5, $6, $7)
               ON CONFLICT(network, size) DO UPDATE SET
               network_id=EXCLUDED.network_id,
               plan_id=EXCLUDED.plan_id,
               cost_price=EXCLUDED.cost_price,
               price=EXCLUDED.price,
               duration=EXCLUDED.duration""",
            network, network_id, size, plan_id, cost_price, float(selling_price), duration
        )


async def delete_plan(network: str, size: str) -> bool:
    """Delete a plan by network and size. Returns True if deleted, False if not found."""
    network = network.upper().strip()
    size = size.upper().strip().replace(" ", "")
    pool = await _get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM data_plans WHERE network = $1 AND size = $2",
            network, size
        )
        return result != "DELETE 0"


# ─── Profit / Gains Analytics ────────────────────────────────────────────────

async def get_profit_stats() -> Dict[str, Any]:
    """Get profit statistics: today, this week, this month, this year, and all-time.
    Only counts completed orders.
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        stats = {}

        # Today
        row = await conn.fetchrow(
            """SELECT COALESCE(SUM(profit), 0) as total_profit,
                      COALESCE(SUM(amount), 0) as total_revenue,
                      COALESCE(SUM(cost_price), 0) as total_cost,
                      COUNT(*) as order_count
               FROM orders
               WHERE status = 'completed'
               AND DATE(created_at) = CURRENT_DATE"""
        )
        stats["today"] = dict(row)

        # This week (last 7 days)
        row = await conn.fetchrow(
            """SELECT COALESCE(SUM(profit), 0) as total_profit,
                      COALESCE(SUM(amount), 0) as total_revenue,
                      COALESCE(SUM(cost_price), 0) as total_cost,
                      COUNT(*) as order_count
               FROM orders
               WHERE status = 'completed'
               AND created_at >= NOW() - INTERVAL '7 days'"""
        )
        stats["week"] = dict(row)

        # This month
        row = await conn.fetchrow(
            """SELECT COALESCE(SUM(profit), 0) as total_profit,
                      COALESCE(SUM(amount), 0) as total_revenue,
                      COALESCE(SUM(cost_price), 0) as total_cost,
                      COUNT(*) as order_count
               FROM orders
               WHERE status = 'completed'
               AND TO_CHAR(created_at, 'YYYY-MM') = TO_CHAR(NOW(), 'YYYY-MM')"""
        )
        stats["month"] = dict(row)

        # This year
        row = await conn.fetchrow(
            """SELECT COALESCE(SUM(profit), 0) as total_profit,
                      COALESCE(SUM(amount), 0) as total_revenue,
                      COALESCE(SUM(cost_price), 0) as total_cost,
                      COUNT(*) as order_count
               FROM orders
               WHERE status = 'completed'
               AND TO_CHAR(created_at, 'YYYY') = TO_CHAR(NOW(), 'YYYY')"""
        )
        stats["year"] = dict(row)

        # All time
        row = await conn.fetchrow(
            """SELECT COALESCE(SUM(profit), 0) as total_profit,
                      COALESCE(SUM(amount), 0) as total_revenue,
                      COALESCE(SUM(cost_price), 0) as total_cost,
                      COUNT(*) as order_count
               FROM orders
               WHERE status = 'completed'"""
        )
        stats["all_time"] = dict(row)

        # Total users
        row = await conn.fetchrow("SELECT COUNT(*) as count FROM users")
        stats["total_users"] = row["count"]

        return stats
