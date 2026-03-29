import sys
sys.stdout.reconfigure(encoding='utf-8')

import asyncio
import logging
from services.llm_service import process_message

logging.basicConfig(level=logging.ERROR)

async def test():
    # Simulate a user asking for a recommendation and then providing a number
    resp = await process_message(12345, "What MTN data should I get for heavy streaming?")
    print("Recommendation:", resp)
    
    resp2 = await process_message(12345, "10GB for 08012345678")
    print("Order:", resp2)

if __name__ == "__main__":
    asyncio.run(test())
