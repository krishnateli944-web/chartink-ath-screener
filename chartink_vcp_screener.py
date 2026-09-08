#!/usr/bin/env python3
"""
Chartink VCP Screener - Automated workflow
1. Scrapes Chartink screener via Firecrawl
2. Runs VCP + Fundamentals analysis on each stock
3. Sends Telegram alerts for NEW qualifying stocks only
4. Saves full analysis to file
"""

import os
import json
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Set

IST = timezone(timedelta(hours=5, minutes=30))

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY")

SEEN_FILE = "seen_vcp_alerts.json"
FULL_LIST_FILE = "vcp_full_analysis.txt"
CHARTINK_URL = "https://chartink.com/screener/kjt-2"
TELEGRAM_MSG_LIMIT = 3500

# Quality filters
MIN_MARKET_CAP = 5000_00_00_000
MIN_ROE = 0.10
MAX_DEBT_EQUITY = 1.0
MIN_PROFIT_MARGIN = 0.05
MAX_PE = 50
MIN_PRICE = 50


def safe_float(val):
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def load_seen() -> Set[str]:
    if not os.path.exists(SEEN_FILE):
        return set()
    with open(SEEN_FILE, "r") as f:
        return set(json.load(f))


def save_seen(seen_set: Set[str]):
    trimmed = list(seen_set)[-1000:]
    with open(SEEN_FILE, "w") as f:
        json.dump(trimmed, f)


def make_key(symbol: str, stage: str, pivot: float) -> str:
    return f"{symbol}|{stage}|{pivot:.0f}"


def fetch_chartink_stocks() -> List[str]:
    """Fetch stock symbols from Chartink screener using Firecrawl."""
    if not FIRECRAWL_API_KEY:
        print("FIRECRAWL_API_KEY not set, skipping Chartink fetch")
        return []
    
    url = "https://api.firecrawl.dev/v1/scrape"
    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "url": CHARTINK_URL,
        "formats": ["markdown"],
        "actions": [
            {"type": "click", "selector": "button:contains('Run'), button:contains('Run Scan'), .btn-primary, input[type='submit']"},
            {"type": "wait", "milliseconds": 8000}
        ]
    }
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        
        if not data.get("success"):
            print(f"Firecrawl scrape failed: {data}")
            return []
        
        markdown = data.get("data", {}).get("markdown", "")
        
        # Parse table
        symbols = []
        for line in markdown.split('\n'):
            if '|' in line and 'Stock Name' not in line and '---' not in line and 'Sr.' not in line:
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 4:
                    symbol = parts[3]  # Symbol column
                    if symbol and symbol.isalpha():
                        symbols.append(symbol)
        
        # Dedup
        symbols = list(dict.fromkeys(symbols))
        print(f"Chartink returned {len(symbols)} symbols")
        
        # Save for reference
        with open('chartink_symbols.json', 'w') as f:
            json.dump({'timestamp': datetime.now(IST).isoformat(), 'symbols': symbols}, f)
        
        return symbols
    except Exception as e:
        print(f"Chartink fetch error: {e}")
        return []


def fetch_stock_data(symbol: str) -> Dict:
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        hist = ticker.history(period="1y")
        info = ticker.info
        
        if hist.empty or len(hist) < 50:
            return {"symbol": symbol, "error": "Insufficient price data"}
        
        hist['SMA_50'] = hist['Close'].rolling(50).mean()
        hist['SMA_150'] = hist['Close'].rolling(150).mean()
        hist['SMA_200'] = hist['Close'].rolling(200).mean()
        hist['Vol_Avg_50'] = hist['Volume'].rolling(50).mean()
        hist['Vol_Avg_20'] = hist['Volume'].rolling(20).mean()
        
        current = hist.iloc[-1]
        
        data = {
            "symbol": symbol,
            "hist": hist,
            "current_price": safe_float(current['Close']),
            "current_volume": safe_float(current['Volume']),
            "sma_50": safe_float(current['SMA_50']),
            "sma_150": safe_float(current['SMA_150']),
            "sma_200": safe_float(current['SMA_200']),
            "vol_avg_50": safe_float(current['Vol_Avg_50']),
            "vol_avg_20": safe_float(current['Vol_Avg_20']),
            "high_52w": safe_float(hist['High'].max()),
            "low_52w": safe_float(hist['Low'].min()),
            "info": info,
            "fundamentals": {
                "eps_growth_yoy": safe_float(info.get("earningsQuarterlyGrowth")),
                "sales_growth_yoy": safe_float(info.get("revenueGrowth")),
                "roe": safe_float(info.get("returnOnEquity")),
                "profit_margin": safe_float(info.get("profitMargins")),
                "debt_to_equity": safe_float(info.get("debtToEquity")),
                "pe_ratio": safe_float(info.get("trailingPE")),
                "market_cap": safe_float(info.get("marketCap")),
                "sector": info.get("sector"),
            }
        }
        return data
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


def check_trend_template(data: Dict) -> Tuple[bool, List[str]]:
    reasons = []
    price = data["current_price"]
    sma_50 = data["sma_50"]
    sma_150 = data["sma_150"]
    sma_200 = data["sma_200"]
    high_52w = data["high_52w"]
    low_52w = data["low_52w"]
    hist = data["hist"]
    
    if None in [price, sma_50, sma_150, sma_200, high_52w, low_52w]:
        return False, ["data incomplete"]
    
    if not (price > sma_150 and price > sma_200):
        reasons.append("Price not above 150/200 SMA")
    if not (sma_150 > sma_200):
        reasons.append("150 SMA not above 200 SMA")
    
    sma_200_series = hist['SMA_200'].dropna()
    if len(sma_200_series) >= 20:
        if not (sma_200_series.iloc[-1] > sma_200_series.iloc[-20]):
            reasons.append("200 SMA not trending up")
    else:
        reasons.append("Insufficient 200 SMA history")
    
    if not (sma_50 > sma_150 > sma_200):
        reasons.append("SMA alignment failed")
    if not (price > sma_50):
        reasons.append("Price not above 50 SMA")
    
    pct_above_low = ((price - low_52w) / low_52w) * 100
    if pct_above_low < 25:
        reasons.append(f"Only {pct_above_low:.0f}% above 52w low")
    
    pct_from_high = ((high_52w - price) / high_52w) * 100
    if pct_from_high > 25:
        reasons.append(f"{pct_from_high:.0f}% below 52w high")
    
    return len(reasons) == 0, reasons


def detect_vcp(data: Dict) -> Dict:
    hist = data["hist"]
    price = data["current_price"]
    vol_avg_50 = data["vol_avg_50"]
    
    if len(hist) < 100:
        return {"error": "Insufficient data"}
    
    recent = hist.tail(120)
    recent_high = recent['High'].max()
    
    closes = recent['Close']
    volumes = recent['Volume']
    
    window = 10
    local_highs = []
    local_lows = []
    
    for i in range(window, len(closes) - window):
        if closes.iloc[i] == closes.iloc[i-window:i+window+1].max():
            local_highs.append((closes.index[i], closes.iloc[i]))
        if closes.iloc[i] == closes.iloc[i-window:i+window+1].min():
            local_lows.append((closes.index[i], closes.iloc[i]))
    
    contractions = []
    for h_idx, h_val in local_highs:
        next_lows = [(idx, val) for idx, val in local_lows if idx > h_idx]
        if next_lows:
            l_idx, l_val = next_lows[0]
            drop_pct = ((h_val - l_val) / h_val) * 100
            vol_at_low = volumes.loc[l_idx] if l_idx in volumes.index else None
            contractions.append({
                "high_date": h_idx, "high_price": h_val,
                "low_date": l_idx, "low_price": l_val,
                "drop_pct": drop_pct, "volume_at_low": vol_at_low
            })
    
    contractions = [c for c in contractions if c["drop_pct"] > 3]
    contractions = contractions[-4:]
    
    sequential = True
    for i in range(1, len(contractions)):
        if contractions[i]["drop_pct"] >= contractions[i-1]["drop_pct"]:
            sequential = False
            break
    
    vol_drying = True
    if len(contractions) >= 2 and contractions[-1]["volume_at_low"] and contractions[-2]["volume_at_low"]:
        if contractions[-1]["volume_at_low"] > contractions[-2]["volume_at_low"]:
            vol_drying = False
    
    if contractions:
        base_weeks = (contractions[-1]["low_date"] - contractions[0]["high_date"]).days / 7
    else:
        base_weeks = 0
    
    pivot = recent_high
    pct_from_pivot = ((pivot - price) / pivot) * 100
    
    if pct_from_pivot < 3:
        stage = "NEAR PIVOT"
    elif pct_from_pivot < 10:
        stage = "APPROACHING PIVOT"
    else:
        stage = "BASE FORMING"
    
    breakout_confirmed = False
    if price > pivot:
        vol_surge = data["current_volume"] / vol_avg_50 if vol_avg_50 and vol_avg_50 > 0 else 0
        if vol_surge >= 1.4:
            breakout_confirmed = True
            stage = "BREAKOUT CONFIRMED"
    
    return {
        "num_contractions": len(contractions),
        "contractions": contractions,
        "sequential": sequential,
        "vol_drying": vol_drying,
        "base_weeks": base_weeks,
        "pivot": pivot,
        "pct_from_pivot": pct_from_pivot,
        "stage": stage,
        "breakout_confirmed": breakout_confirmed,
    }


def check_fundamentals(data: Dict) -> Tuple[bool, List[str], Dict]:
    f = data["fundamentals"]
    reasons = []
    passed = True
    
    eps_growth = f.get("eps_growth_yoy")
    sales_growth = f.get("sales_growth_yoy")
    roe = f.get("roe")
    profit_margin = f.get("profit_margin")
    debt_equity = f.get("debt_to_equity")
    
    if eps_growth is not None:
        if eps_growth < 0.20:
            reasons.append(f"EPS growth {eps_growth*100:.1f}% < 20%")
            passed = False
    else:
        reasons.append("EPS growth N/A")
        passed = False
    
    if sales_growth is not None:
        if sales_growth < 0.20:
            reasons.append(f"Sales growth {sales_growth*100:.1f}% < 20%")
            passed = False
    else:
        reasons.append("Sales growth N/A")
        passed = False
    
    if roe is not None:
        if roe < 0.15:
            reasons.append(f"ROE {roe*100:.1f}% < 15%")
            passed = False
    else:
        reasons.append("ROE N/A")
        passed = False
    
    if debt_equity is not None:
        if debt_equity > 1.0:
            reasons.append(f"D/E {debt_equity:.2f} > 1.0")
            passed = False
    else:
        reasons.append("D/E N/A")
        passed = False
    
    if profit_margin is not None and profit_margin < 0.05:
        reasons.append(f"Margin {profit_margin*100:.1f}% < 5%")
        passed = False
    
    return passed, reasons, {
        "eps_growth": eps_growth, "sales_growth": sales_growth,
        "roe": roe, "profit_margin": profit_margin, "debt_to_equity": debt_equity
    }


def check_quality_filters(fundamentals: Dict) -> Tuple[bool, List[str]]:
    reasons = []
    price = safe_float(fundamentals.get("current_price"))
    if price is not None and price < MIN_PRICE:
        reasons.append(f"Price ₹{price:.0f} < ₹{MIN_PRICE}")
    
    mcap = safe_float(fundamentals.get("market_cap"))
    if mcap is not None and mcap < MIN_MARKET_CAP:
        reasons.append(f"MCap ₹{mcap/1e7:.0f}Cr < ₹{MIN_MARKET_CAP/1e7:.0f}Cr")
    
    roe = safe_float(fundamentals.get("roe"))
    if roe is not None and roe < MIN_ROE:
        reasons.append(f"ROE {roe*100:.1f}% < {MIN_ROE*100:.0f}%")
    
    de = safe_float(fundamentals.get("debt_to_equity"))
    if de is not None and de > MAX_DEBT_EQUITY:
        reasons.append(f"D/E {de:.2f} > {MAX_DEBT_EQUITY}")
    
    pm = safe_float(fundamentals.get("profit_margin"))
    if pm is not None and pm < MIN_PROFIT_MARGIN:
        reasons.append(f"Margin {pm*100:.1f}% < {MIN_PROFIT_MARGIN*100:.0f}%")
    
    pe = safe_float(fundamentals.get("pe_ratio"))
    if pe is not None and pe > MAX_PE:
        reasons.append(f"P/E {pe:.1f} > {MAX_PE}")
    
    return len(reasons) == 0, reasons


def analyze_stock(symbol: str) -> Optional[Dict]:
    print(f"  Analyzing {symbol}...")
    data = fetch_stock_data(symbol)
    if "error" in data:
        return None
    
    trend_pass, trend_reasons = check_trend_template(data)
    if not trend_pass:
        return None
    
    vcp = detect_vcp(data)
    if "error" in vcp:
        return None
    
    fund_pass, fund_reasons, fund_snapshot = check_fundamentals(data)
    quality_pass, quality_reasons = check_quality_filters(data["fundamentals"])
    
    # Confidence
    confidence = "LOW"
    if trend_pass and vcp["sequential"] and vcp["vol_drying"] and vcp["base_weeks"] >= 5 and fund_pass and quality_pass:
        confidence = "HIGH"
    elif trend_pass and vcp["sequential"] and fund_pass:
        confidence = "MEDIUM"
    elif trend_pass and fund_pass:
        confidence = "MEDIUM"
    
    # Only return if MEDIUM or HIGH confidence
    if confidence == "LOW":
        return None
    
    # Stop loss
    if vcp["contractions"]:
        final_low = vcp["contractions"][-1]["low_price"]
        stop_loss = min(final_low, vcp["pivot"] * 0.92)
    else:
        stop_loss = vcp["pivot"] * 0.92
    
    return {
        "symbol": symbol,
        "name": data["info"].get("longName", data["info"].get("shortName", symbol)),
        "current_price": data["current_price"],
        "vcp": vcp,
        "fund_pass": fund_pass,
        "fund_reasons": fund_reasons,
        "fund_snapshot": fund_snapshot,
        "quality_pass": quality_pass,
        "quality_reasons": quality_reasons,
        "pivot": vcp["pivot"],
        "stop_loss": stop_loss,
        "confidence": confidence,
        "sector": data["fundamentals"].get("sector"),
    }


def format_telegram(result: Dict) -> str:
    vcp = result['vcp']
    fs = result['fund_snapshot']
    lines = []
    lines.append(f"{'🟢🟢' if result['confidence']=='HIGH' else '🟢'} *{result['symbol']}* — {result['confidence']}")
    lines.append(f"📰 Chartink screener hit")
    lines.append(f"💰 ₹{result['current_price']:.0f} | Pivot: ₹{result['pivot']:.0f} | SL: ₹{result['stop_loss']:.0f}")
    lines.append(f"📊 EPS: {fs.get('eps_growth',0)*100:.0f}% | Sales: {fs.get('sales_growth',0)*100:.0f}% | ROE: {fs.get('roe',0)*100:.0f}% | D/E: {fs.get('debt_to_equity',0):.2f}")
    lines.append(f"📈 VCP: {vcp['num_contractions']} contractions, {vcp['base_weeks']:.1f}w base, {vcp['stage']}")
    return "\n".join(lines)


def format_full(result: Dict) -> str:
    vcp = result['vcp']
    fs = result['fund_snapshot']
    lines = []
    lines.append(f"={'='*50}")
    lines.append(f"{result['symbol']} — {result.get('name','')} — {result['confidence']}")
    lines.append(f"Price: ₹{result['current_price']:.2f} | Pivot: ₹{result['pivot']:.2f} | SL: ₹{result['stop_loss']:.2f}")
    lines.append(f"VCP: {vcp['num_contractions']} contractions, sequential: {'Y' if vcp['sequential'] else 'N'}, vol dry: {'Y' if vcp['vol_drying'] else 'N'}, {vcp['base_weeks']:.1f}w, {vcp['stage']}")
    lines.append(f"Fund: EPS {fs.get('eps_growth',0)*100:.1f}%, Sales {fs.get('sales_growth',0)*100:.1f}%, ROE {fs.get('roe',0)*100:.1f}%, D/E {fs.get('debt_to_equity',0):.2f}")
    if result['quality_reasons']:
        lines.append(f"Quality issues: {'; '.join(result['quality_reasons'])}")
    return "\n".join(lines)


def send_telegram(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, data=payload, timeout=10)
        return r.ok
    except:
        return False


def send_batched(lines: List[str]):
    if not lines:
        return
    header = f"📈 *VCP Screener Alert* — {datetime.now(IST).strftime('%d-%b %H:%M')} IST\n\n"
    chunk = header
    for line in lines:
        if len(chunk) + len(line) > TELEGRAM_MSG_LIMIT:
            send_telegram(chunk)
            chunk = ""
        chunk += line + "\n\n"
    if chunk.strip():
        send_telegram(chunk)


def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing")
        return
    
    seen = load_seen()
    
    # Fetch Chartink stocks
    chartink_symbols = fetch_chartink_stocks()
    
    # Also include watchlist
    watchlist = ["DIVISLAB", "JSWINFRA", "SONACOMS", "LAURUSLABS", "TVSMOTOR", "OFSS", "RRKABEL"]
    all_symbols = list(dict.fromkeys(chartink_symbols + watchlist))
    
    print(f"Screening {len(all_symbols)} unique stocks...")
    
    alerts = []
    full_analyses = []
    
    for symbol in all_symbols:
        result = analyze_stock(symbol)
        if not result:
            continue
        
        full_analyses.append(format_full(result))
        
        key = make_key(result['symbol'], result['vcp']['stage'], result['vcp']['pivot'])
        if key not in seen:
            seen.add(key)
            alerts.append(format_telegram(result))
            print(f"  ✅ NEW ALERT: {result['symbol']} ({result['confidence']})")
        else:
            print(f"  ⏭️ Already seen: {result['symbol']}")
    
    save_seen(seen)
    
    if alerts:
        send_batched(alerts)
        print(f"Sent {len(alerts)} new alerts")
    else:
        print("No new qualifying stocks")
    
    if full_analyses:
        header = f"VCP Full Analysis — {datetime.now(IST).strftime('%d-%b-%Y %H:%M')} IST\n"
        header += f"Screened: {len(all_symbols)} | Qualified: {len(full_analyses)}\n\n"
        with open(FULL_LIST_FILE, "w") as f:
            f.write(header + "\n\n".join(full_analyses))
        print(f"Full analysis saved to {FULL_LIST_FILE}")


if __name__ == "__main__":
    main()