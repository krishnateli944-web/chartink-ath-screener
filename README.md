# Chartink ATH Screener

Automated GitHub Action that fetches stocks hitting All-Time Highs from Chartink and sends them to Telegram daily.

## Setup

### 1. GitHub Repository Secrets
Add these secrets to your GitHub repository (Settings → Secrets and variables → Actions):

| Secret | Description |
|--------|-------------|
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID (user ID or group ID) |

### 2. Get Telegram Credentials

**Bot Token:**
1. Message @BotFather on Telegram
2. Send `/newbot` and follow instructions
3. Copy the token

**Chat ID:**
1. Message @userinfobot or @getmyid_bot
2. Copy your user ID (or group ID for groups)

### 3. Local Testing
```bash
# Install dependencies
pip install requests beautifulsoup4 lxml python-telegram-bot

# Set environment variables
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"

# Run
python fetch_ath_stocks.py
```

## Schedule
Runs automatically at **9:00 AM UTC (2:30 PM IST)** on weekdays (Mon-Fri).

## Manual Trigger
Go to Actions → Chartink ATH Screener → Run workflow

## Files
- `.github/workflows/chartink-ath.yml` - GitHub Actions workflow
- `fetch_ath_stocks.py` - Main Python script
- `ath_stocks.json` - Output file (generated on each run)