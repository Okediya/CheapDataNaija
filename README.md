# CheapDataNaija Bot 🇳🇬

A smart AI-powered Telegram bot that sells affordable MTN, Airtel, and Glo data bundles instantly using an in-bot wallet system.

**Powered by:** Google Gemini 2.5 Flash · Paystack · SMEDATA.NG

---

## Features

- **Conversational AI** — Type naturally: _"Buy 2GB MTN data for 08012345678"_
- **In-Bot Wallet** — Fund once, buy data instantly without repeated payment redirects
- **Paystack Integration** — Secure wallet funding via card, bank transfer, or USSD
- **Auto Webhook** — Wallet is credited automatically when Paystack confirms payment
- **Instant Delivery** — Data is delivered to the recipient phone immediately after purchase
- **Fallback Menu** — Inline keyboard for users who prefer button navigation
- **Order History** — Track all your purchases and wallet transactions

## Project Structure

```
cheapdatanaija/
├── .env                  # Your credentials (never commit this)
├── .env.example          # Template for credentials
├── .gitignore
├── requirements.txt
├── config.py             # Settings loader
├── database.py           # SQLite database layer
├── main.py               # Webhook server entry point
├── bot/
│   ├── __init__.py
│   └── handlers.py       # Telegram command & message handlers
└── services/
    ├── __init__.py
    ├── gemini_service.py  # Gemini AI with tool-calling
    ├── wallet_service.py  # Wallet operations
    ├── smedata_service.py # VTU data purchase
    └── paystack_service.py # Payment processing
```

## Setup

### Prerequisites

- Python 3.10 or higher
- A Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Google Gemini API key (from [Google AI Studio](https://aistudio.google.com/))
- Paystack account with test/live keys
- SMEDATA.NG API token

### 1. Clone & Install

```bash
cd cheapdatanaija
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your credentials:

```
BOT_TOKEN=your_telegram_bot_token
GOOGLE_API_KEY=your_google_gemini_api_key
PAYSTACK_SECRET_KEY=sk_test_xxxxxxxxxxxxxxxxxxxx
PAYSTACK_PUBLIC_KEY=pk_test_xxxxxxxxxxxxxxxxxxxx
SMEDATA_TOKEN=your_smedata_api_token
WEBHOOK_HOST=https://your-domain.com
WEBHOOK_PATH=/webhook/bot
SERVER_PORT=8080
DATABASE_PATH=cheapdatanaija.db
```

### 3. Set Up Webhooks

Your bot needs a public HTTPS URL for webhooks to work. Options:

**For local development:**
```bash
# Install ngrok: https://ngrok.com
ngrok http 8080
# Copy the https URL and set WEBHOOK_HOST in .env
```

**For production (Railway / Render / VPS):**
- Set `WEBHOOK_HOST` to your public domain (e.g., `https://cheapdatanaija.onrender.com`)

**Paystack Webhook:**
- Go to Paystack Dashboard → Settings → API Keys & Webhooks
- Set Webhook URL to: `https://your-domain.com/webhook/paystack`

### 4. Run the Bot

```bash
python main.py
```

You should see:
```
Starting CheapDataNaija Bot on port 8080...
Database initialized.
Webhook set to: https://your-domain.com/webhook/bot
```

## Testing the Full Flow

### Step 1: Start the Bot
Open Telegram, find your bot, and send `/start`.

### Step 2: Check Data Prices
Type: _"Show me MTN data prices"_

### Step 3: Fund Your Wallet
Type: _"Fund my wallet with 1000 naira"_
- Click the Paystack payment link
- Complete payment with test card: `4084 0840 8408 4081` (expiry: any future date, CVV: 408, OTP: 0000)
- Your wallet is credited automatically

### Step 4: Buy Data
Type: _"Buy 2GB MTN data for 08012345678"_
- The bot shows a summary with the price and your balance
- Reply _"Yes"_ to confirm
- Data is purchased instantly, wallet is debited

### Step 5: Check Balance & History
- _"Check my balance"_
- _"Show my orders"_
- _"Show my wallet history"_

## Data Prices

| Network | 1GB | 2GB | 3GB | 5GB | 10GB |
|---------|-----|-----|-----|-----|------|
| MTN     | ₦280 | ₦550 | ₦800 | ₦1,300 | ₦2,500 |
| Airtel  | ₦270 | ₦530 | ₦780 | ₦1,250 | — |
| Glo     | ₦260 | ₦510 | ₦760 | ₦1,200 | — |

## Deployment (Free 24/7 Hosting)

### Render.com (Recommended)

1. Push code to GitHub
2. Create a new **Web Service** on Render
3. Set the environment variables from `.env`
4. Set Build Command: `pip install -r requirements.txt`
5. Set Start Command: `python main.py`
6. Update `WEBHOOK_HOST` to your Render URL

### Railway.app

1. Connect your GitHub repo
2. Railway auto-detects Python
3. Set environment variables in the Railway dashboard
4. Update `WEBHOOK_HOST` to your Railway URL

### Procfile (for Railway/Heroku)

```
web: python main.py
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Bot not responding | Check that `WEBHOOK_HOST` matches your public URL |
| Payment not crediting | Verify Paystack webhook URL is set correctly |
| Data purchase failing | Check `SMEDATA_TOKEN` is valid and has balance |
| Gemini errors | Verify `GOOGLE_API_KEY` is active |

## License

MIT
