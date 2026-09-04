#!/usr/bin/env python3
"""
Chartink All-Time High (ATH) Screener - Improved Version
Uses Chartink's scan API endpoint for reliable data fetching.
"""

import os
import requests
import json
from datetime import datetime
import telegram
import asyncio

# Chartink API endpoints
SCREENER_URL = "https://chartink.com/screener/all-time-high-100000513"
SCAN_API_URL = "https://chartink.com/backtest/process"  # Chartink's internal API

# Telegram credentials
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def get_scan_clause():
    """Extract the scan clause from the screener page."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        response = requests.get(SCREENER_URL, headers=headers, timeout=30)
        
        # Look for scan_clause in the page
        import re
        # Chartink stores the scan clause in a meta tag or script
        patterns = [
            r'scan_clause["\s:=]+([^"\'}]+)',
            r'scanClause["\s:=]+([^"\'}]+)',
            r'condition["\s:=]+([^"\'}]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response.text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # Default ATH condition - stocks where close = 52-week high
        return "close = max(high, 252) and close > 0"
        
    except Exception as e:
        print(f"Error getting scan clause: {e}")
        return "close = max(high, 252) and close > 0"


def fetch_stocks_via_api(scan_clause):
    """Fetch stocks using Chartink's backtest/process API."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': 'https://chartink.com',
            'Referer': SCREENER_URL,
        }
        
        # First get CSRF token
        session = requests.Session()
        session.get(SCREENER_URL, headers=headers, timeout=30)
        csrf_token = session.cookies.get('XSRF-TOKEN') or session.cookies.get('csrftoken')
        
        if csrf_token:
            headers['X-CSRF-TOKEN'] = csrf_token
        
        # Post to scan API
        data = {
            'scan_clause': scan_clause,
            'timeframe': 'daily',
        }
        
        response = session.post(SCAN_API_URL, headers=headers, data=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            return result.get('data', [])
        
        return []
        
    except Exception as e:
        print(f"API fetch error: {e}")
        return []


def fetch_stocks_html():
    """Fallback: Fetch stocks by parsing HTML table."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        response = requests.get(SCREENER_URL, headers=headers, timeout=30)
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        stocks = []
        # Find table with stock data
        table = soup.find('table')
        if table:
            rows = table.find_all('tr')
            for row in rows[1:]:  # Skip header
                cols = row.find_all(['td', 'th'])
                if len(cols) >= 4:
                    # Try to extract link for symbol
                    name_link = cols[1].find('a') if len(cols) > 1 else None
                    symbol_link = cols[2].find('a') if len(cols) > 2 else None
                    
                    name = name_link.get_text(strip=True) if name_link else cols[1].get_text(strip=True)
                    symbol = symbol_link.get_text(strip=True) if symbol_link else cols[2].get_text(strip=True)
                    close = cols[3].get_text(strip=True) if len(cols) > 3 else ""
                    change = cols[4].get_text(strip=True) if len(cols) > 4 else ""
                    volume = cols[5].get_text(strip=True) if len(cols) > 5 else ""
                    
                    if symbol and symbol not in ['Symbol', 'SYMBOL', '']:
                        stocks.append({
                            'name': name,
                            'symbol': symbol,
                            'close': close,
                            'change_pct': change,
                            'volume': volume
                        })
        
        return stocks
        
    except Exception as e:
        print(f"HTML fetch error: {e}")
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
    
    for i, stock in enumerate(stocks[:25], 1):  # Top 25
        name = stock.get('name', 'N/A')
        symbol = stock.get('symbol', 'N/A')
        close = stock.get('close', 'N/A')
        change = stock.get('change_pct', 'N/A')
        volume = stock.get('volume', 'N/A')
        
        # Format change with emoji
        change_emoji = "🟢" if change and change.replace('%', '').replace('+', '').replace('-', '').replace('.', '').isdigit() and float(change.replace('%', '').replace('+', '')) >= 0 else "🔴"
        
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


def main():
    print("🔍 Fetching Chartink ATH stocks...")
    
    # Try API first
    scan_clause = get_scan_clause()
    print(f"📋 Scan clause: {scan_clause}")
    
    stocks = fetch_stocks_via_api(scan_clause)
    
    # Fallback to HTML parsing
    if not stocks:
        print("🔄 API returned no data, trying HTML parsing...")
        stocks = fetch_stocks_html()
    
    print(f"✅ Found {len(stocks)} stocks")
    
    if stocks:
        for s in stocks[:5]:
            print(f"  - {s['symbol']}: {s['name']} @ ₹{s['close']} ({s['change_pct']})")
    
    message = format_message(stocks)
    save_results(stocks)
    
    # Send to Telegram
    asyncio.run(send_telegram_message(message))
    
    print("🎉 Done!")


if __name__ == "__main__":
    main()