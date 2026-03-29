"""
CheapDataNaija Bot — Configuration
Loads all settings from .env file.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID", "")

# Groq Llama 3.3
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Paystack
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "")
PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY", "")

# SMEDATA.NG
SMEDATA_TOKEN = os.getenv("SMEDATA_TOKEN", "")
SMEDATA_BASE_URL = "https://smedata.ng/wp-json/api/v1/"

# Webhook — Render auto-injects RENDER_EXTERNAL_URL
WEBHOOK_HOST = os.getenv("RENDER_EXTERNAL_URL", os.getenv("WEBHOOK_HOST", "https://your-domain.com"))
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook/bot")
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# Server — Railway/Render inject PORT; fall back to SERVER_PORT or 8080
SERVER_PORT = int(os.getenv("PORT", os.getenv("SERVER_PORT", "8080")))

# Database
DATABASE_PATH = os.getenv("DATABASE_PATH", "cheapdatanaija.db")
