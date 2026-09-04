#!/usr/bin/env python3
"""
Chartink All-Time High (ATH) Screener - Using Playwright for JS rendering
"""

import os
import asyncio
import json
from datetime import datetime
import telegram

SCREENER_URL = "https://chartink.com/screener/all-time-high-100000513"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


async def fetch_stocks_playwright():
    """Fetch stocks using Playwright to render JavaScript."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("Playwright not installed, installing...")
        import subprocess
        subprocess.run(["pip", "install", "playwright"], check=True)
        subprocess.run(["playwright", "install", "chromium"], check=True)
        from playwright.async_api import async_playwright
    
    stocks = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            # Navigate to screener
            await page.goto(SCREENER_URL, wait_until="networkidle", timeout=60000)
            
            # Wait for the stock table to load
            await page.wait_for_selector("table", timeout=30000)
            
            # Wait a bit more for data to populate
            await page.wait_for_timeout(5000)
            
            # Extract stock data from the table
            rows = await page.query_selector_all("table tbody tr")
            
            for row in rows:
                cols = await row.query_selector_all("td")
                if len(cols) >= 4:
                    try:
                        name = await cols[1].inner_text()
                        symbol = await cols[2].inner_text()
                        close = await cols[3].inner_text()
                        change = await cols[4].inner_text() if len(cols) > 4 else ""
                        volume = await cols[5].inner_text() if len(cols) > 5 else ""
                        
                        name = name.strip()
                        symbol = symbol.strip()
                        close = close.strip()
                        change = change.strip()
                        volume = volume.strip()
                        
                        if symbol and symbol not in ['Symbol', 'SYMBOL', '']:
                            stocks.append({
                                'name': name,
                                'symbol': symbol,
                                'close': close,
                                'change_pct': change,
                                'volume': volume
                            })
                    except Exception as e:
                        continue
            
            await browser.close()
            
        except Exception as e:
            print(f"Playwright error: {e}")
            await browser.close()
    
    return stocks


def fetch_stocks_api():
    """Try Chartink's backtest API endpoint."""
    import requests
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': 'https://chartink.com',
            'Referer': SCREENER_URL,
        }
        
        session = requests.Session()
        # Get the page first to establish session/cookies
        resp = session.get(SCREENER_URL, headers=headers, timeout=30)
        
        # Look for CSRF token
        csrf_token = session.cookies.get('XSRF-TOKEN') or session.cookies.get('csrftoken')
        if csrf_token:
            headers['X-CSRF-TOKEN'] = csrf_token
        
        # Try the scan API
        scan_clause = "close = max(high, 252) and close > 0"
        data = {
            'scan_clause': scan_clause,
            'timeframe': 'daily',
        }
        
        resp = session.post("https://chartink.com/backtest/process", headers=headers, data=data, timeout=30)
        
        if resp.status_code == 200:
            result = resp.json()
            return result.get('data', [])
        
    except Exception as e:
        print(f"API error: {e}")
    
    return []


def format_message(stocks):
    """Format the stock list for Telegram message."""
    date_str = datetime.now().strftime("%d %b %Y, %I:%M %p IST")
    
    if not stocks:
        return (
            f"📊 **Chartink ATH Screener**\n"
            f"📅 {date_str}\n\n"
            f"No stocks found at All-Time High today.\n\n"
            f"🔗 [View on Chartink]({SCREENER_URL})\n"
            f"#ATH #AllTimeHigh #Chartink #StockMarket #NSE"
        )
    
    message = f"📊 **Chartink ATH Screener - All Time High Stocks**\n"
    message += f"📅 {date_str}\n"
    message += f"🔗 [View on Chartink]({SCREENER_URL})\n\n"
    
    for i, stock in enumerate(stocks[:25], 1):
        name = stock.get('name', 'N/A')
        symbol = stock.get('symbol', 'N/A')
        close = stock.get('close', 'N/A')
        change = stock.get('change_pct', 'N/A')
        volume = stock.get('volume', 'N/A')
        
        change_emoji = "🟢" if change and change.replace('%', '').replace('+', '').replace('-', '').replace('.', '').isdigit() and float(change.replace('%', '').replace('+', '') or '0') >= 0 else "🔴"
        
        message += f"**{i}. {name} ({symbol})**\n"
        message += f"   💰 ₹{close} | {change_emoji} {change} | 📊 Vol: {volume}\n\n"
    
    if len(stocks) > 25:
        message += f"... and {len(stocks) - 25} more stocks.\n"
    
    message += "\n#ATH #AllTimeHigh #Chartink #StockMarket #NSE"
    return message


async def send_telegram_message(message):
    """Send message to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials not configured")
        return False
    
    try:
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        print("✅ Message sent to Telegram successfully")
        return True
    except Exception as e:
        print(f"❌ Error sending to Telegram: {e}")
        return False


def save_results(stocks):
    """Save results to JSON file."""
    with open('ath_stocks.json', 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'count': len(stocks),
            'stocks': stocks
        }, f, indent=2)


async def main():
    print("🔍 Fetching Chartink ATH stocks...")
    
    # Try API first
    stocks = fetch_stocks_api()
    
    # If API fails, use Playwright
    if not stocks:
        print("🔄 API returned no data, trying Playwright...")
        stocks = await fetch_stocks_playwright()
    
    print(f"✅ Found {len(stocks)} stocks")
    
    if stocks:
        for s in stocks[:5]:
            print(f"  - {s['symbol']}: {s['name']} @ ₹{s['close']} ({s['change_pct']})")
    
    message = format_message(stocks)
    save_results(stocks)
    
    # Send to Telegram
    await send_telegram_message(message)
    
    print("🎉 Done!")


if __name__ == "__main__":
    asyncio.run(main())