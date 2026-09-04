#!/usr/bin/env python3
"""
NSE All-Time High (ATH) Screener - Using yfinance for reliable data
"""

import os
import json
import yfinance as yf
from datetime import datetime
import telegram

# Major NSE stock symbols that work with yfinance (verified working symbols)
NSE_SYMBOLS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
    "LT.NS", "ASIANPAINT.NS", "AXISBANK.NS", "MARUTI.NS", "SUNPHARMA.NS",
    "TITAN.NS", "ULTRACEMCO.NS", "WIPRO.NS", "NESTLEIND.NS", "POWERGRID.NS",
    "NTPC.NS", "BAJFINANCE.NS", "HCLTECH.NS", "JSWSTEEL.NS",
    "COALINDIA.NS", "ONGC.NS", "TATASTEEL.NS",
    "INDUSINDBK.NS", "GRASIM.NS", "BRITANNIA.NS", "CIPLA.NS", "DRREDDY.NS",
    "EICHERMOT.NS", "HEROMOTOCO.NS", "BAJAJ-AUTO.NS", "TECHM.NS", "UPL.NS",
    "SHREECEM.NS", "DIVISLAB.NS", "BPCL.NS", "IOC.NS", "GAIL.NS",
    "HINDALCO.NS", "VEDL.NS", "TATACONSUM.NS", "M&M.NS", "SBILIFE.NS",
    "ADANIENT.NS", "ADANIPORTS.NS", "HDFCLIFE.NS", "TATAPOWER.NS",
]

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def fetch_ath_stocks_yfinance():
    """Find stocks at/near all-time high using yfinance."""
    ath_stocks = []
    
    for symbol in NSE_SYMBOLS:
        try:
            ticker = yf.Ticker(symbol)
            # Get 1 year of data
            hist = ticker.history(period="1y")
            
            if hist.empty or len(hist) < 2:
                continue
            
            current_price = hist['Close'].iloc[-1]
            high_52w = hist['High'].max()
            
            # Check if current price is at or near 52-week high (within 3%)
            if current_price >= high_52w * 0.97:
                prev_close = hist['Close'].iloc[-2]
                change_pct = ((current_price - prev_close) / prev_close) * 100
                volume = hist['Volume'].iloc[-1]
                
                # Get company name
                info = ticker.info
                name = info.get('longName', info.get('shortName', symbol.replace('.NS', '')))
                
                ath_stocks.append({
                    'symbol': symbol.replace('.NS', ''),
                    'name': name,
                    'close': round(current_price, 2),
                    'change_pct': f"{change_pct:+.2f}%",
                    'volume': f"{int(volume):,}",
                    'high_52w': round(high_52w, 2),
                })
                
        except Exception as e:
            continue
    
    # Sort by how close to 52-week high (closest first)
    ath_stocks.sort(key=lambda x: x['close'] / x['high_52w'], reverse=True)
    
    return ath_stocks


def format_message(stocks):
    """Format the stock list for Telegram message."""
    date_str = datetime.now().strftime("%d %b %Y, %I:%M %p IST")
    
    if not stocks:
        return (
            f"📊 **NSE ATH Screener (yfinance)**\n"
            f"📅 {date_str}\n\n"
            f"No stocks found near All-Time High today.\n\n"
            f"#ATH #AllTimeHigh #NSE #StockMarket"
        )
    
    message = f"📊 **NSE ATH Screener - Stocks Near 52-Week High**\n"
    message += f"📅 {date_str}\n\n"
    
    for i, stock in enumerate(stocks[:25], 1):
        name = stock.get('name', 'N/A')
        symbol = stock.get('symbol', 'N/A')
        close = stock.get('close', 'N/A')
        change = stock.get('change_pct', 'N/A')
        volume = stock.get('volume', 'N/A')
        high_52w = stock.get('high_52w', 'N/A')
        
        change_val = str(change).replace('%', '').replace('+', '').replace('-', '')
        try:
            change_emoji = "🟢" if float(change_val or '0') >= 0 else "🔴"
        except:
            change_emoji = "🔴"
        
        # Calculate % from 52w high
        from_high = ((high_52w - close) / high_52w) * 100
        
        message += f"**{i}. {name} ({symbol})**\n"
        message += f"   💰 ₹{close} | {change_emoji} {change} | 📊 Vol: {volume}\n"
        message += f"   📈 52W High: ₹{high_52w} ({from_high:.1f}% away)\n\n"
    
    if len(stocks) > 25:
        message += f"... and {len(stocks) - 25} more stocks.\n"
    
    message += "\n#ATH #AllTimeHigh #NSE #StockMarket #yfinance"
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
    print("🔍 Fetching ATH stocks via yfinance...")
    
    stocks = fetch_ath_stocks_yfinance()
    
    print(f"✅ Found {len(stocks)} stocks near 52-week high")
    
    if stocks:
        for s in stocks[:5]:
            print(f"  - {s['symbol']}: {s['name']} @ ₹{s['close']} ({s['change_pct']}) - 52W High: ₹{s['high_52w']}")
    
    message = format_message(stocks)
    save_results(stocks)
    
    # Send to Telegram
    await send_telegram_message(message)
    
    print("🎉 Done!")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())