
import requests

# ... (Previous imports)
import yfinance as yf
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor

import json
import os

# Load Nikkei 225 Tickers from JSON
try:
    # Assuming nikkei_names.json is in the same directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(current_dir, 'nikkei_names.json')
    
    with open(json_path, 'r', encoding='utf-8') as f:
        nikkei_data = json.load(f)
        tickers = list(nikkei_data.keys())
except Exception as e:
    # Fallback if JSON fails (Critical Backup)
    print(f"Error loading nikkei_names.json: {e}")
    tickers = [
        "7203", "9984", "8306", "6758", "6861", "6954", "6501", "8035", "6098", "6367",
        "4063", "8058", "9432", "4568", "9433", "7974", "8316", "3382", "7267", "6902"
    ]

# Deduplicate
tickers = list(set(tickers)) 

# LIMIT TO TOP 5 for Fast Debugging
# LIMIT TO TOP 50 for Cloud Stability (Restored)
# tickers = tickers[:50] # UNCOMMENT TO LIMIT IF NEEDED

# Helper for debug logging
def safe_import_st():
    try:
        import streamlit as st
        return st
    except ImportError:
        class DummyST:
            def write(self, *args, **kwargs): print(*args, **kwargs)
            def error(self, *args, **kwargs): print("ERROR:", *args, **kwargs)
        return DummyST()

def analyze_stock(code, hist_data=None, fundamentals=None):
    try:
        # If batch data is provided, use it
        if hist_data is not None:
            hist = hist_data
            ticker = None
        else:
            # Single mode: Fetch data
            ticker = yf.Ticker(f"{code}.T")
            hist = ticker.history(period="6mo")
            
        if hist.empty:
            return None
            
        current_price = hist['Close'].iloc[-1]
        
        # MA Calculation
        ma5 = hist['Close'].rolling(window=5).mean().iloc[-1]
        ma25 = hist['Close'].rolling(window=25).mean().iloc[-1]
        ma75 = hist['Close'].rolling(window=75).mean().iloc[-1]
        
        # Previous MA25 (5 days ago) for slope
        ma25_prev = hist['Close'].rolling(window=25).mean().iloc[-6]
        
        # ATR Calculation
        try:
            high_low = hist['High'] - hist['Low']
            high_close = np.abs(hist['High'] - hist['Close'].shift())
            low_close = np.abs(hist['Low'] - hist['Close'].shift())
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(14).mean().iloc[-1]
        except:
            atr = 0

        # --- EXTENDED TECHNICAL ANALYSIS ---
        try:
            # 1. MACD (12, 26, 9)
            ema12 = hist['Close'].ewm(span=12, adjust=False).mean()
            ema26 = hist['Close'].ewm(span=26, adjust=False).mean()
            macd = ema12 - ema26
            signal = macd.ewm(span=9, adjust=False).mean()
            macd_val = macd.iloc[-1]
            signal_val = signal.iloc[-1]
            
            # 2. Bollinger Bands (20, 2sigma)
            ma20 = hist['Close'].rolling(window=20).mean()
            std20 = hist['Close'].rolling(window=20).std()
            bb_upper = ma20 + (2 * std20)
            bb_lower = ma20 - (2 * std20)
            # FIX: Ensure scalar value for bb_pos
            bb_pos_series = (current_price - bb_lower) / (bb_upper - bb_lower)
            bb_pos = bb_pos_series.iloc[-1]
            
            # 3. Ichimoku Cloud (9, 26, 52)
            high9 = hist['High'].rolling(window=9).max()
            low9 = hist['Low'].rolling(window=9).min()
            tenkan = (high9 + low9) / 2
            
            high26 = hist['High'].rolling(window=26).max()
            low26 = hist['Low'].rolling(window=26).min()
            kijun = (high26 + low26) / 2
            
            senkou_a = ((tenkan + kijun) / 2).shift(26)
            senkou_b = ((hist['High'].rolling(window=52).max() + hist['Low'].rolling(window=52).min()) / 2).shift(26)
            
            # Latest values
            tenkan_val = tenkan.iloc[-1]
            kijun_val = kijun.iloc[-1]
            senkou_a_val = senkou_a.iloc[-1]
            senkou_b_val = senkou_b.iloc[-1]
            kumo_top = max(senkou_a_val, senkou_b_val)
            kumo_bottom = min(senkou_a_val, senkou_b_val)

            # RSI
            delta = hist['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs)).iloc[-1]
            
            # Volume
            vol_ma25 = hist['Volume'].rolling(window=25).mean().iloc[-1]
            current_vol = hist['Volume'].iloc[-1]
            vol_ratio = current_vol / vol_ma25 if vol_ma25 > 0 else 1.0
            
            # Historical Volatility (HV)
            ln_ret = np.log(hist['Close'] / hist['Close'].shift(1))
            hv = ln_ret.rolling(window=20).std().iloc[-1] * np.sqrt(250) * 100

        except Exception as e:
            # st.error(f"Technical Calc Error: {e}")
            return None

        # 3. Fundamentals
        pbr, per = 0, 0
        
        # Try to fetch from ticker.info if available (needed for partial parallel mode)
        if ticker:
            try:
                # Use fast_info if possible for price, but PBR/PER needs info
                # To avoid blocking too long, we wrap in try
                info = ticker.info
                pbr = info.get('priceToBook', 0) or 0
                per = info.get('trailingPE', 0) or 0
            except:
                pass
        
        if fundamentals:
            pbr = fundamentals.get('pbr', pbr)
            per = fundamentals.get('per', per)

        # --- v7.2 REBOUND STRATEGY SCORING (Smooth) ---
        # Goal: Continuous scoring distribution (no 10pt steps)
        
        score_trend = 0.0
        score_dip = 0.0
        score_timing = 0.0
        
        ma75_prev = hist['Close'].rolling(window=75).mean().iloc[-2]
        
        # 1. Trend Health (Max 20) - Binary is fine here
        if ma75 > ma75_prev:
            score_trend += 10
        if ma25 > ma25_prev:
            score_trend += 10
            
        if ma75 < ma75_prev:
            score_trend = -100 # Discard
        
        # 2. Dip Potential (Max 50) - Continuous Curve
        # Ideal Spot: -0.5% (Slightly below MA25)
        
        dev_25 = (current_price - ma25) / ma25 * 100
        dev_75 = (current_price - ma75) / ma75 * 100
        
        # Calculate MA25 Score (Primary)
        # Formula: 50 - |Deviation - (-0.5)| * Weight
        # Weight 12 means: +/- 1% error = -12 pts.
        raw_score_25 = 50 - (abs(dev_25 - (-0.5)) * 12)
        
        # Calculate MA75 Score (Secondary - Deep Dip)
        # Center at -1.0% (Rebound zone), Max 40 pts
        raw_score_75 = 40 - (abs(dev_75 - (-1.0)) * 8)
        
        score_dip = max(0, raw_score_25, raw_score_75)

        # 3. Timing (Max 30) - Continuous Curve
        # Ideal RSI: 40
        
        raw_score_timing = 30 - (abs(rsi - 40) * 0.8)
        score_timing = max(0, raw_score_timing)
        
        # Overheat Penalty (Exponential)
        if rsi > 65:
            score_timing -= (rsi - 65) * 2 # -10pts at RSI 70
            
        total_score = score_trend + score_dip + score_timing
        
        # Final Adjustments
        score = min(100, int(total_score))
        if score < 0: score = 0
        
        # --- v7.2 Clean Up ---
        score_short = 0 
        
        # --- FEATURE TAGS & REASON ---
        short_reason = []
        if score >= 80: short_reason.append("絶好の押し目")
        elif score >= 60: short_reason.append("押し目圏内")
        
        if score_trend >= 20: short_reason.append("上昇トレンド")
        if score_dip >= 40: short_reason.append("MAタッチ")
        if 30 <= rsi <= 50: short_reason.append("売られすぎ")

        # --- COMMENTARY GENERATION ---
        commentary = []
        commentary.append(f"【判定】 スコア: {score}点 (反発狙い v7.2)")
        
        trend_str = "上昇中" if score_trend >= 20 else "弱い"
        commentary.append(f"・トレンド: {trend_str}")
        commentary.append(f"・MA25乖離: {dev_25:+.2f}%")
        commentary.append(f"・RSI: {rsi:.1f}")

        commentary.append("【スコア内訳】")
        commentary.append(f"・トレンド: {int(score_trend)}/20")
        commentary.append(f"・押し目度: {int(score_dip)}/50")
        commentary.append(f"・タイミング: {int(score_timing)}/30")
        
        final_commentary = "\n".join(commentary)
        
        return {
            "Code": code,
            "Price": current_price,
            "Score": score,
            "ScoreShort": score_short, # Deprecated
            "MA25": ma25,
            "Deviation": dev_25, # MA25 Deviation
            "RSI": rsi,
            "PBR": pbr,
            "PER": per,
            "Yield": 0,
            "RR": 0,
            "Details": "、".join(short_reason) if short_reason else "特になし",
            "AnalysisSummary": final_commentary,
            "ScoreDetail": {
                "Trend": int(score_trend),
                "Dip": int(score_dip),
                "Timing": int(score_timing)
            }
        }
        
    except Exception as e:
        safe_import_st().error(f"Error in analyze_stock({code}): {e}")
        return None

def get_next_earnings_date(code):
    try:
        stock = yf.Ticker(f"{code}.T")
        
        # 1. Try Calendar (standard)
        try:
            cal = stock.calendar
            if cal is not None and isinstance(cal, dict):
                dates = cal.get('Earnings Date', [])
                if dates:
                     d = dates[0]
                     return str(d).split(' ')[0]
        except:
            pass
            
        # 2. Try Info (fallback)
        try:
            info = stock.info
            ts = info.get('earningsTimestamp')
            if ts:
                from datetime import datetime
                dt = datetime.fromtimestamp(ts)
                return dt.strftime('%Y-%m-%d')
        except:
            pass
            
        return "-"
    except:
        return "-"

def get_scored_stocks(status_callback=None):
    try:
        import streamlit as st
    except ImportError:
        return []
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = []
    
    if not tickers:
        st.error("Tickers list is empty!")
        return []
        
    total_tickers = len(tickers)
    processed_count = 0
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    status_text.text(f"Starting analysis of {total_tickers} stocks...")
    
    # Parallel Execution
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_code = {executor.submit(analyze_stock, code): code for code in tickers}
        
        for future in as_completed(future_to_code):
            code = future_to_code[future]
            processed_count += 1
            
            try:
                res = future.result()
                if res and isinstance(res, dict) and 'Score' in res:
                    results.append(res)
            except Exception as e:
                print(f"Error fetching {code}: {e}")
            
            # Update Progress
            progress = processed_count / total_tickers
            progress_bar.progress(progress)
            status_text.text(f"Analyzing... ({processed_count}/{total_tickers})")
            
            if status_callback:
                status_callback(progress)
                
    status_text.text(f"Analysis Complete! Found {len(results)} valid stocks.")
    time.sleep(0.5)
    status_text.empty()
    progress_bar.empty()
                
    # Sort by Score Descending
    results.sort(key=lambda x: x.get('Score', 0), reverse=True)
    return results

def main():
    print("Collecting data and analyzing scores for Nikkei 225 candidates...")
    
    def print_progress(p):
        print(f"Progress: {p*100:.0f}%", end="\r")
        
    results = get_scored_stocks(status_callback=print_progress)
    print("\nDone.")
    
    # Fetch Earnings for Top 10 Only (to save time)
    top10 = results[:10]
    print("Fetching earnings dates for top 10...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        # Create a dict of futures
        future_to_code = {executor.submit(get_next_earnings_date, res['Code']): res for res in top10}
        for future in future_to_code:
            res = future_to_code[future]
            res['Earnings'] = future.result()
    
    print("\n### Nikkei 225 Strategy Score Ranking (Top 10)")
    print("| Rank | Code | Score | Price | Dist. MA25 (%) | Earnings | R/R | Factors |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    
    for i, res in enumerate(top10):
        earnings = res.get('Earnings', '-')
        print(f"| {i+1} | {res['Code']} | **{res['Score']}** | {res['Price']:,.0f} | {res['Deviation']:.1f}% | {earnings} | {res['RR']:.2f} | {res['Details']} |")

if __name__ == "__main__":
    main()
