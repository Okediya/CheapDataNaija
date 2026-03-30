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

# Groq Llama 3.3 (supports multiple comma-separated keys for rotation)
_groq_keys_raw = os.getenv("GROQ_API_KEY", "")
GROQ_API_KEYS = [k.strip() for k in _groq_keys_raw.split(",") if k.strip()]

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

# Database (PostgreSQL)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/cheapdatanaija")
