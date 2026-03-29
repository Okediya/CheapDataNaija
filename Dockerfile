# ─── CheapDataNaija Bot — Production Dockerfile ─────────────────────────────
FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Default port (Railway injects $PORT automatically)
ENV PORT=8080
EXPOSE $PORT

# Run the bot
CMD ["python", "main.py"]
