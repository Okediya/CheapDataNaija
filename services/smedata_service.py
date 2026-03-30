"""
CheapDataNaija Bot — SMEDATA.NG VTU Service
Handles data bundle pricing and purchase via SMEDATA.NG API.
"""

import httpx
import json
import logging
from config import SMEDATA_TOKEN, SMEDATA_BASE_URL

from database import get_all_plans, get_plan

logger = logging.getLogger(__name__)

async def get_prices(network: str = None) -> dict:
    """Get available data plans and prices.
    
    Args:
        network: Optional filter by network name.
                 If None, returns all networks.
    
    Returns:
        Dict of network -> {size: price} mappings.
    """
    plans = await get_all_plans()
    prices_dict = {}
    for p in plans:
        net = p["network"]
        if net not in prices_dict:
            prices_dict[net] = {}
        prices_dict[net][p["size"]] = p["price"]
        
    if network:
        network = network.upper().strip()
        if network in prices_dict:
            return {network: prices_dict[network]}
        return {}
    return prices_dict


async def get_price(network: str, size: str) -> float | None:
    """Get the selling price for a specific plan. Returns None if not found."""
    plan = await get_plan(network, size)
    if plan:
        return plan["price"]
    return None


async def get_plan_details(network: str, size: str) -> dict | None:
    """Get full plan details including cost_price and selling price. Returns None if not found."""
    plan = await get_plan(network, size)
    return plan


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

    plan = await get_plan(network, size)
    if not plan:
        return {"success": False, "message": f"Plan {size} not available for {network}"}

    network_id = plan["network_id"]
    plan_id = plan["plan_id"]

    url = f"{SMEDATA_BASE_URL}data"
    params = {
        "token": SMEDATA_TOKEN,
        "network": network.lower(),
        "phone": phone,
        "size": plan_id,
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
