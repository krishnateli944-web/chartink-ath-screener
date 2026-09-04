#!/usr/bin/env python3
"""
Swing News Analyzer - Fetches market news, analyzes mentioned stocks with yfinance,
and sends swing trade signals to Telegram.
"""

import os
import json
import requests
import yfinance as yf
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Set, Optional

IST = timezone(timedelta(hours=5, minutes=30))

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
ALPHA_VANTAGE_API_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY")

WATCHLIST_FILE = "watchlist.txt"
SEEN_FILE = "seen_swing_news.json"
TELEGRAM_MSG_LIMIT = 3500

# Keywords that signal potential swing opportunities
SWING_BULLISH_KEYWORDS = [
    "order", "contract", "award", "bags", "wins", "bagging",
    "financial result", "results", "profit", "growth", "expansion",
    "capex", "capacity", "new plant", "acquisition", "merger",
    "partnership", "joint venture", "investment", "fund raise",
    "ipo", "qip", "rights issue", "buyback", "dividend",
    "bonus", "split", "upgraded", "target raised", "reiterate buy",
    "outperform", "accumulate", "strong", "beat", "surge", "jump",
    "record", "highest", "best", "milestone", "breakthrough"
]

SWING_BEARISH_KEYWORDS = [
    "resign", "resignation", "default", "fraud", "raid", "sebi",
    "investigation", "downgrade", "loss", "postpone", "delay",
    "insolvency", "bankrupt", "qualified opinion", "show cause",
    "penalty", "fine", "litigation", "strike", "lockout", "suspend",
    "auditor", "cbi", "ed ", "search and seizure", "warning",
    "concern", "weak", "miss", "below", "cut", "reduce", "lower",
    "sell", "underperform", "avoid", "risk", "debt", "npa"
]

# News sources to scrape
NEWS_SOURCES = [
    {
        "name": "Moneycontrol",
        "url": "https://www.moneycontrol.com/rss/latestnews.xml",
        "type": "rss"
    },
    {
        "name": "Economic Times Markets",
        "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "type": "rss"
    },
    {
        "name": "Business Standard Markets",
        "url": "https://www.business-standard.com/rss/markets-106.rss",
        "type": "rss"
    },
    {
        "name": "NSE Announcements",
        "url": "https://www.nseindia.com/api/corporate-announcements?index=equities",
        "type": "nse_api"
    }
]

# Common NSE stock symbols for matching (top 200 liquid stocks)
NSE_SYMBOLS = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "HINDUNILVR", "ITC",
    "SBIN", "BHARTIARTL", "KOTAKBANK", "LT", "BAJFINANCE", "ASIANPAINT",
    "MARUTI", "HCLTECH", "AXISBANK", "SUNPHARMA", "TITAN", "ULTRACEMCO",
    "TATAMOTORS", "NESTLEIND", "POWERGRID", "NTPC", "ONGC", "COALINDIA",
    "JSWINFRA", "SONACOMS", "LAURUSLABS", "TVSMOTOR", "DIVISLAB", "KALYANJWL",
    "OFSS", "RRKABEL", "ADANIENT", "ADANIPORTS", "ADANIGREEN", "ADANIPOWER",
    "TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "SAIL", "JINDALSTEL",
    "BPCL", "IOC", "HINDPETRO", "GAIL", "PETRONET", "IGL", "MGL",
    "DMART", "TRENT", "ZOMATO", "NYKAA", "PAYTM", "POLICYBZR",
    "BAJAJFINSV", "BAJAJ-AUTO", "HEROMOTOCO", "TVSMOTOR", "EICHERMOT",
    "M&M", "TATAMOTORS", "MARUTI", "ASHOKLEY", "ESCORTS",
    "CIPLA", "DRREDDY", "SUNPHARMA", "LUPIN", "BIOCON", "CADILAHC",
    "AUROPHARMA", "TORNTPHARM", "ALKEM", "GLENMARK", "NATCOPHARM",
    "TECHM", "WIPRO", "LTIM", "MPHASIS", "PERSISTENT", "COFORGE",
    "LTTS", "KPITTECH", "TATAELXSI", "CYIENT", "AFFLE",
    "PIDILITIND", "BERGER", "KANSAINER", "AKZOINDIA", "GRASIM",
    "SHREECEM", "ACC", "AMBUJACEM", "RAMCOCEM", "HEIDELBERG",
    "HAVELLS", "POLYCAB", "KEI", "RRKABEL", "FINCABLES",
    "VOLTAS", "BLUESTARCO", "WHIRLPOOL", "CROMPTON", "HAVELLS",
    "GODREJCP", "DABUR", "MARICO", "COLPAL", "EMAMILTD",
    "PAGEIND", "RELAXO", "BATAINDIA", "METROBRAND", "CAMPUS",
    "TRENT", "DMART", "TRENT", "SHOPERSTOP", "VBAZAR",
    "JUBLFOOD", "DEVYANI", "SAPPHIRE", "BURGERKING", "WESTLIFE",
    "INDIGO", "SPICEJET", "JETAIRWAYS", "AIRLINES",
    "IRCTC", "IRCON", "RVNL", "IRFC", "RAILTEL",
    "COCHINSHIP", "MAZDOCK", "GRSE", "BEL", "HAL",
    "BDL", "ASTRA", "PARAS", "DATAPATTNS", "KELTECH",
    "ZYDUSLIFE", "GLAXO", "PFIZER", "SANOFI", "ABBOTINDIA",
    "MANKIND", "ERIS", "TORNTPHARM", "ALKEM", "NATCOPHARM",
    "CHOLAFIN", "SHRIRAMFIN", "BAJAJFINSV", "MUTHOOTFIN", "MANAPPURAM",
    "IIFL", "MOTILALOFS", "ANGELONE", "ZERODHA", "ICICISEC",
    "HDFCAMC", "NIPPONAMC", "ADITYABIRLA", "UTI", "SBIMF",
    "CAMS", "KFINTECH", "LINKINTIME", "COMPUAGE", "MAHINDRAFIN"
]


def load_list(path: str) -> List[str]:
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return [line.strip().upper() for line in f if line.strip() and not line.startswith("#")]


def load_seen() -> Set[str]:
    if not os.path.exists(SEEN_FILE):
        return set()
    with open(SEEN_FILE, "r") as f:
        return set(json.load(f))


def save_seen(seen_set: Set[str]):
    trimmed = list(seen_set)[-1000:]
    with open(SEEN_FILE, "w") as f:
        json.dump(trimmed, f)


def make_key(item: Dict) -> str:
    return f"{item.get('symbol', '')}|{item.get('title', '')[:60]}|{item.get('date', '')[:10]}"


def matches_any(text: str, keywords: List[str]) -> bool:
    text_l = text.lower()
    return any(k in text_l for k in keywords)


def extract_symbols(text: str) -> List[str]:
    """Extract NSE symbols from text."""
    text_upper = text.upper()
    found = []
    for symbol in NSE_SYMBOLS:
        # Match whole word or with .NS suffix
        if f" {symbol} " in f" {text_upper} " or f"{symbol}.NS" in text_upper or f"{symbol} " in text_upper:
            found.append(symbol)
    return list(set(found))  # dedupe


def fetch_rss_feed(url: str) -> List[Dict]:
    """Fetch and parse RSS feed."""
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        
        # Simple XML parsing for RSS
        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.content)
        
        items = []
        for item in root.findall(".//item"):
            title = item.find("title")
            description = item.find("description")
            link = item.find("link")
            pub_date = item.find("pubDate")
            
            items.append({
                "title": title.text if title is not None else "",
                "description": description.text if description is not None else "",
                "link": link.text if link is not None else "",
                "pub_date": pub_date.text if pub_date is not None else "",
                "source": "rss"
            })
        return items
    except Exception as e:
        print(f"RSS fetch failed for {url}: {e}")
        return []


def fetch_nse_announcements() -> List[Dict]:
    """Fetch NSE corporate announcements."""
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "*/*",
        })
        session.get("https://www.nseindia.com", timeout=10)
        
        url = "https://www.nseindia.com/api/corporate-announcements?index=equities"
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        items = []
        for item in data:
            items.append({
                "symbol": item.get("symbol", ""),
                "title": item.get("desc", ""),
                "description": item.get("attchmntText", "") or "",
                "date": item.get("an_dt", ""),
                "source": "nse"
            })
        return items
    except Exception as e:
        print(f"NSE announcements fetch failed: {e}")
        return []


def get_stock_fundamentals(symbol: str) -> Dict:
    """Get key fundamentals from yfinance."""
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        info = ticker.info
        
        # Get recent price history for technicals
        hist = ticker.history(period="3mo")
        
        fundamentals = {
            "symbol": symbol,
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "pb_ratio": info.get("priceToBook"),
            "debt_to_equity": info.get("debtToEquity"),
            "roe": info.get("returnOnEquity"),
            "profit_margin": info.get("profitMargins"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "beta": info.get("beta"),
            "dividend_yield": info.get("dividendYield"),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
            "avg_volume": info.get("averageVolume"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
        }
        
        # Technical indicators from price history
        if not hist.empty:
            current = hist["Close"].iloc[-1]
            sma_20 = hist["Close"].rolling(20).mean().iloc[-1]
            sma_50 = hist["Close"].rolling(50).mean().iloc[-1]
            sma_200 = hist["Close"].rolling(200).mean().iloc[-1] if len(hist) >= 200 else None
            
            # RSI calculation
            delta = hist["Close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            fundamentals.update({
                "sma_20": sma_20,
                "sma_50": sma_50,
                "sma_200": sma_200,
                "rsi": rsi.iloc[-1] if not rsi.empty else None,
                "price_vs_sma20": ((current - sma_20) / sma_20 * 100) if sma_20 else None,
                "price_vs_sma50": ((current - sma_50) / sma_50 * 100) if sma_50 else None,
                "volume_ratio": hist["Volume"].iloc[-1] / hist["Volume"].rolling(20).mean().iloc[-1] if hist["Volume"].rolling(20).mean().iloc[-1] > 0 else None,
            })
        
        return fundamentals
    except Exception as e:
        print(f"Fundamentals fetch failed for {symbol}: {e}")
        return {"symbol": symbol, "error": str(e)}


def analyze_swing_potential(symbol: str, news_text: str, fundamentals: Dict) -> Dict:
    """Analyze swing trade potential based on news sentiment and fundamentals."""
    
    # News sentiment
    bullish_score = sum(1 for k in SWING_BULLISH_KEYWORDS if k in news_text.lower())
    bearish_score = sum(1 for k in SWING_BEARISH_KEYWORDS if k in news_text.lower())
    
    news_sentiment = "BULLISH" if bullish_score > bearish_score else "BEARISH" if bearish_score > bullish_score else "NEUTRAL"
    
    # Fundamental score
    fund_score = 0
    fund_signals = []
    
    pe = fundamentals.get("pe_ratio")
    if pe and pe < 25:
        fund_score += 1
        fund_signals.append(f"PE: {pe:.1f} (attractive)")
    elif pe and pe > 40:
        fund_score -= 1
        fund_signals.append(f"PE: {pe:.1f} (expensive)")
    
    roe = fundamentals.get("roe")
    if roe and roe > 0.15:
        fund_score += 1
        fund_signals.append(f"ROE: {roe*100:.1f}% (strong)")
    elif roe and roe < 0.05:
        fund_score -= 1
        fund_signals.append(f"ROE: {roe*100:.1f}% (weak)")
    
    debt_equity = fundamentals.get("debt_to_equity")
    if debt_equity and debt_equity < 0.5:
        fund_score += 1
        fund_signals.append(f"D/E: {debt_equity:.2f} (low debt)")
    elif debt_equity and debt_equity > 2:
        fund_score -= 1
        fund_signals.append(f"D/E: {debt_equity:.2f} (high debt)")
    
    rev_growth = fundamentals.get("revenue_growth")
    if rev_growth and rev_growth > 0.1:
        fund_score += 1
        fund_signals.append(f"Rev Growth: {rev_growth*100:.1f}%")
    elif rev_growth and rev_growth < -0.05:
        fund_score -= 1
        fund_signals.append(f"Rev Growth: {rev_growth*100:.1f}% (declining)")
    
    # Technical score
    tech_score = 0
    tech_signals = []
    
    rsi = fundamentals.get("rsi")
    if rsi:
        if rsi < 30:
            tech_score += 2
            tech_signals.append(f"RSI: {rsi:.1f} (oversold)")
        elif rsi < 40:
            tech_score += 1
            tech_signals.append(f"RSI: {rsi:.1f} (approaching oversold)")
        elif rsi > 70:
            tech_score -= 2
            tech_signals.append(f"RSI: {rsi:.1f} (overbought)")
        elif rsi > 60:
            tech_score -= 1
            tech_signals.append(f"RSI: {rsi:.1f} (approaching overbought)")
        else:
            tech_signals.append(f"RSI: {rsi:.1f} (neutral)")
    
    price_vs_sma20 = fundamentals.get("price_vs_sma20")
    if price_vs_sma20 is not None:
        if price_vs_sma20 > 5:
            tech_score += 1
            tech_signals.append(f"Above SMA20 by {price_vs_sma20:.1f}%")
        elif price_vs_sma20 < -5:
            tech_score -= 1
            tech_signals.append(f"Below SMA20 by {abs(price_vs_sma20):.1f}%")
    
    price_vs_sma50 = fundamentals.get("price_vs_sma50")
    if price_vs_sma50 is not None:
        if price_vs_sma50 > 10:
            tech_score += 1
            tech_signals.append(f"Above SMA50 by {price_vs_sma50:.1f}% (trend)")
        elif price_vs_sma50 < -10:
            tech_score -= 1
            tech_signals.append(f"Below SMA50 by {abs(price_vs_sma50):.1f}% (downtrend)")
    
    vol_ratio = fundamentals.get("volume_ratio")
    if vol_ratio and vol_ratio > 1.5:
        tech_score += 1
        tech_signals.append(f"Volume: {vol_ratio:.1f}x avg (strong interest)")
    
    # 52-week position
    high_52 = fundamentals.get("52w_high")
    low_52 = fundamentals.get("52w_low")
    current = fundamentals.get("current_price")
    if high_52 and low_52 and current:
        pct_from_high = (high_52 - current) / high_52 * 100
        pct_from_low = (current - low_52) / low_52 * 100
        if pct_from_high < 5:
            tech_score += 1
            tech_signals.append(f"Near 52W high ({pct_from_high:.1f}% away)")
        if pct_from_low < 10:
            tech_score -= 1
            tech_signals.append(f"Near 52W low ({pct_from_low:.1f}% away)")
    
    total_score = fund_score + tech_score + (2 if news_sentiment == "BULLISH" else -2 if news_sentiment == "BEARISH" else 0)
    
    if total_score >= 4:
        recommendation = "STRONG BUY"
        emoji = "🟢🟢"
    elif total_score >= 2:
        recommendation = "BUY"
        emoji = "🟢"
    elif total_score >= 0:
        recommendation = "NEUTRAL"
        emoji = "🟡"
    elif total_score >= -2:
        recommendation = "SELL"
        emoji = "🔴"
    else:
        recommendation = "STRONG SELL"
        emoji = "🔴🔴"
    
    return {
        "symbol": symbol,
        "recommendation": recommendation,
        "emoji": emoji,
        "total_score": total_score,
        "news_sentiment": news_sentiment,
        "bullish_keywords": bullish_score,
        "bearish_keywords": bearish_score,
        "fund_score": fund_score,
        "fund_signals": fund_signals,
        "tech_score": tech_score,
        "tech_signals": tech_signals,
        "current_price": fundamentals.get("current_price"),
        "pe_ratio": fundamentals.get("pe_ratio"),
        "rsi": fundamentals.get("rsi"),
    }


def send_telegram(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, data=payload, timeout=10)
        return r.ok
    except Exception as e:
        print(f"Telegram send failed: {e}")
        return False


def send_batched(lines: List[str]):
    if not lines:
        return
    header = f"📈 *Swing Trade News Alerts* — {datetime.now(IST).strftime('%d-%b-%Y %H:%M')} IST\n\n"
    chunk = header
    for line in lines:
        if len(chunk) + len(line) > TELEGRAM_MSG_LIMIT:
            send_telegram(chunk)
            chunk = ""
        chunk += line + "\n\n"
    if chunk.strip():
        send_telegram(chunk)


def format_analysis(analysis: Dict, news_title: str, news_source: str) -> str:
    """Format analysis for Telegram."""
    lines = []
    lines.append(f"{analysis['emoji']} *{analysis['symbol']}* — {analysis['recommendation']} (Score: {analysis['total_score']})")
    lines.append(f"📰 *News:* {news_title[:120]}")
    lines.append(f"📍 *Source:* {news_source}")
    lines.append(f"💭 *News Sentiment:* {analysis['news_sentiment']} (Bullish: {analysis['bullish_keywords']}, Bearish: {analysis['bearish_keywords']})")
    
    if analysis.get("current_price"):
        lines.append(f"💰 *Price:* ₹{analysis['current_price']:.2f}")
    if analysis.get("pe_ratio"):
        lines.append(f"📊 *P/E:* {analysis['pe_ratio']:.1f}")
    if analysis.get("rsi"):
        lines.append(f"📈 *RSI:* {analysis['rsi']:.1f}")
    
    if analysis["fund_signals"]:
        lines.append(f"🏢 *Fundamentals:* {'; '.join(analysis['fund_signals'])}")
    if analysis["tech_signals"]:
        lines.append(f"📉 *Technicals:* {'; '.join(analysis['tech_signals'])}")
    
    return "\n".join(lines)


def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing")
        return

    watchlist = load_list(WATCHLIST_FILE)
    seen = load_seen()
    
    all_news_items = []
    
    # Fetch from all sources
    for source in NEWS_SOURCES:
        print(f"Fetching from {source['name']}...")
        if source["type"] == "rss":
            items = fetch_rss_feed(source["url"])
        elif source["type"] == "nse_api":
            items = fetch_nse_announcements()
        else:
            items = []
        
        for item in items:
            item["source_name"] = source["name"]
        all_news_items.extend(items)
    
    print(f"Total news items fetched: {len(all_news_items)}")
    
    alert_lines = []
    analyzed_symbols = set()
    
    for item in all_news_items:
        key = make_key(item)
        if key in seen:
            continue
        seen.add(key)
        
        title = item.get("title", "")
        description = item.get("description", "")
        full_text = f"{title} {description}"
        source_name = item.get("source_name", "Unknown")
        
        # Extract symbols from news
        symbols = extract_symbols(full_text)
        
        # Also check if NSE announcement has explicit symbol
        if item.get("symbol"):
            symbols.append(item["symbol"].upper())
        
        symbols = list(set(symbols))  # dedupe
        
        for symbol in symbols:
            if symbol in analyzed_symbols:
                continue
            analyzed_symbols.add(symbol)
            
            print(f"Analyzing {symbol}...")
            fundamentals = get_stock_fundamentals(symbol)
            
            if "error" in fundamentals:
                continue
            
            analysis = analyze_swing_potential(symbol, full_text, fundamentals)
            
            # Only alert for actionable signals (BUY/SELL or watchlist stocks)
            is_watchlist = symbol in watchlist
            is_actionable = analysis["recommendation"] in ["STRONG BUY", "BUY", "SELL", "STRONG SELL"]
            
            if is_actionable or is_watchlist:
                formatted = format_analysis(analysis, title, source_name)
                if is_watchlist:
                    formatted = f"⭐ *WATCHLIST STOCK*\n{formatted}"
                alert_lines.append(formatted)
                print(f"  -> {analysis['recommendation']} (Score: {analysis['total_score']})")
    
    save_seen(seen)
    
    if alert_lines:
        send_batched(alert_lines)
        print(f"Sent {len(alert_lines)} swing alerts to Telegram")
    else:
        print("No actionable swing signals this run")


if __name__ == "__main__":
    main()