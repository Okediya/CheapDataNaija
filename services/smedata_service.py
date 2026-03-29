"""
CheapDataNaija Bot — SMEDATA.NG VTU Service
Handles data bundle pricing and purchase via SMEDATA.NG API.
"""

import httpx
import json
import logging
from config import SMEDATA_TOKEN, SMEDATA_BASE_URL

logger = logging.getLogger(__name__)

# ─── Hard-coded selling prices (editable) ────────────────────────────────────
DATA_PRICES = {
    "MTN": {
        "1GB": 280,
        "2GB": 550,
        "3GB": 800,
        "5GB": 1300,
        "10GB": 2500,
    },
    "AIRTEL": {
        "1GB": 270,
        "2GB": 530,
        "3GB": 780,
        "5GB": 1250,
    },
    "GLO": {
        "1GB": 260,
        "2GB": 510,
        "3GB": 760,
        "5GB": 1200,
    },
}

# Map network names to SMEDATA API network IDs
NETWORK_IDS = {
    "MTN": "1",
    "AIRTEL": "2",
    "GLO": "3",
    "9MOBILE": "4",
}

# Map size strings to SMEDATA plan IDs (these may need adjustment based on actual API)
PLAN_IDS = {
    "MTN": {
        "1GB": "1",
        "2GB": "2",
        "3GB": "3",
        "5GB": "5",
        "10GB": "10",
    },
    "AIRTEL": {
        "1GB": "1",
        "2GB": "2",
        "3GB": "3",
        "5GB": "5",
    },
    "GLO": {
        "1GB": "1",
        "2GB": "2",
        "3GB": "3",
        "5GB": "5",
    },
}


def get_prices(network: str = None) -> dict:
    """Get available data plans and prices.
    
    Args:
        network: Optional filter by network name (MTN, AIRTEL, GLO).
                 If None, returns all networks.
    
    Returns:
        Dict of network -> {size: price} mappings.
    """
    if network:
        network = network.upper().strip()
        if network in DATA_PRICES:
            return {network: DATA_PRICES[network]}
        return {}
    return DATA_PRICES


def get_price(network: str, size: str) -> float | None:
    """Get the price for a specific plan. Returns None if not found."""
    network = network.upper().strip()
    size = size.upper().strip()
    return DATA_PRICES.get(network, {}).get(size)


def normalize_network(text: str) -> str | None:
    """Normalize network name from user input."""
    text = text.upper().strip()
    for net in DATA_PRICES:
        if net in text:
            return net
    return None


def normalize_size(text: str) -> str | None:
    """Normalize data size from user input (e.g. '2gb' → '2GB')."""
    text = text.upper().strip().replace(" ", "")
    all_sizes = set()
    for plans in DATA_PRICES.values():
        all_sizes.update(plans.keys())
    if text in all_sizes:
        return text
    return None


async def buy_data(network: str, size: str, phone: str) -> dict:
    """Purchase a data bundle via SMEDATA.NG API.
    
    Args:
        network: Network name (MTN, AIRTEL, GLO)
        size: Data size (1GB, 2GB, etc.)
        phone: Recipient phone number
    
    Returns:
        API response dict with status and details.
    """
    network = network.upper().strip()
    size = size.upper().strip()

    if network not in NETWORK_IDS:
        return {"success": False, "message": f"Unsupported network: {network}"}

    if network not in PLAN_IDS or size not in PLAN_IDS.get(network, {}):
        return {"success": False, "message": f"Plan {size} not available for {network}"}

    network_id = NETWORK_IDS[network]
    plan_id = PLAN_IDS[network][size]

    url = f"{SMEDATA_BASE_URL}data"
    params = {
        "token": SMEDATA_TOKEN,
        "network": network_id,
        "phone": phone,
        "plan": plan_id,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            logger.info(f"SMEDATA API response [{response.status_code}]: {response.text}")

            if response.status_code == 200:
                data = response.json()
                # Check for success in response
                if data.get("status") == "success" or data.get("code") == "success":
                    return {
                        "success": True,
                        "message": f"{size} {network} data bundle sent to {phone} successfully.",
                        "details": data
                    }
                else:
                    return {
                        "success": False,
                        "message": data.get("message", "The data provider returned an error. Please try again."),
                        "details": data
                    }
            else:
                return {
                    "success": False,
                    "message": f"API request failed with status {response.status_code}. Please try again later.",
                }
    except httpx.TimeoutException:
        logger.error(f"SMEDATA API timeout for {network} {size} to {phone}")
        return {"success": False, "message": "The request timed out. Please try again."}
    except Exception as e:
        logger.error(f"SMEDATA API error: {e}")
        return {"success": False, "message": f"An error occurred: {str(e)}"}
