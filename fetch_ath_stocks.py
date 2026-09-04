#!/usr/bin/env python3
"""
Chartink All-Time High (ATH) Screener - Simple approach using requests with proper headers
"""

import os
import json
import requests
from datetime import datetime
import telegram

SCREENER_URL = "https://chartink.com/screener/all-time-high-100000513"
SCAN_API_URL = "https://chartink.com/backtest/process"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def fetch_stocks():
    """Fetch stocks using Chartink's scan API with proper session handling."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': 'https://chartink.com',
            'Referer': SCREENER_URL,
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        
        session = requests.Session()
        session.headers.update(headers)
        
        # First GET request to get cookies and CSRF token
        resp = session.get(SCREENER_URL, timeout=30)
        
        # Get CSRF token from cookies
        csrf_token = session.cookies.get('XSRF-TOKEN') or session.cookies.get('csrftoken')
        
        # Also try meta tag
        if not csrf_token:
            import re
            csrf_match = re.search(r'name="csrf-token" content="([^"]+)"', resp.text)
            if csrf_match:
                csrf_token = csrf_match.group(1)
        
        # Try X-CSRF-TOKEN header
        if csrf_token:
            session.headers['X-CSRF-TOKEN'] = csrf_token
        
        # The scan clause - try different variations
        scan_clauses = [
            "close = max(high, 252) and close > 0",
            "close >= max(high, 252) and close > 0",
            "close > ref(close, 1) and close = max(high, 252)",
        ]
        
        for scan_clause in scan_clauses:
            data = {
                'scan_clause': scan_clause,
                'timeframe': 'daily',
            }
            
            resp = session.post(SCAN_API_URL, data=data, timeout=60)
            
            if resp.status_code == 200:
                try:
                    result = resp.json()
                    stocks = result.get('data', [])
                    if stocks:
                        print(f"Success with clause: {scan_clause}")
                        return stocks
                except:
                    pass
            
            # Try alternative endpoint
            alt_url = "https://chartink.com/screener/process"
            resp = session.post(alt_url, data=data, timeout=60)
            if resp.status_code == 200:
                try:
                    result = resp.json()
                    stocks = result.get('data', [])
                    if stocks:
                        print(f"Success with alt endpoint and clause: {scan_clause}")
                        return stocks
                except:
                    pass
        
        # If all fail, try to get data from the page HTML (it might have embedded data)
        # Check for data in script tags
        import re
        # Look for stock data in the page
        stock_data_match = re.search(r'var\s+stockData\s*=\s*(\[.*?\]);', resp.text, re.DOTALL)
        if stock_data_match:
            try:
                stocks = json.loads(stock_data_match.group(1))
                return stocks
            except:
                pass
        
    except Exception as e:
        print(f"Error: {e}")
    
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
        # Handle different possible data structures
        if isinstance(stock, dict):
            name = stock.get('nsecode', stock.get('name', stock.get('symbol', 'N/A')))
            symbol = stock.get('symbol', stock.get('nsecode', 'N/A'))
            close = stock.get('close', stock.get('price', 'N/A'))
            change = stock.get('per_chg', stock.get('change_pct', 'N/A'))
            volume = stock.get('volume', 'N/A')
        else:
            # If it's a list/array
            symbol = str(stock[0]) if len(stock) > 0 else 'N/A'
            name = str(stock[1]) if len(stock) > 1 else 'N/A'
            close = str(stock[2]) if len(stock) > 2 else 'N/A'
            change = str(stock[3]) if len(stock) > 3 else 'N/A'
            volume = str(stock[4]) if len(stock) > 4 else 'N/A'
        
        change_val = str(change).replace('%', '').replace('+', '').replace('-', '')
        try:
            change_emoji = "🟢" if float(change_val or '0') >= 0 else "🔴"
        except:
            change_emoji = "🔴"
        
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
    
    stocks = fetch_stocks()
    
    print(f"✅ Found {len(stocks)} stocks")
    
    if stocks:
        for s in stocks[:5]:
            if isinstance(s, dict):
                print(f"  - {s.get('symbol', s.get('nsecode', 'N/A'))}: {s.get('name', 'N/A')} @ ₹{s.get('close', 'N/A')}")
            else:
                print(f"  - {s}")
    
    message = format_message(stocks)
    save_results(stocks)
    
    # Send to Telegram
    await send_telegram_message(message)
    
    print("🎉 Done!")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())