
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
tickers = tickers[:5]

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
        # DEBUG ENTRY
        st = safe_import_st()
        st.write(f"DEBUG: Analyzing {code} (Inside function)")

        # If batch data is provided, use it
        if hist_data is not None:
            hist = hist_data
            ticker = None
        else:
            # Single mode: Fetch data
            ticker = yf.Ticker(f"{code}.T")
            hist = ticker.history(period="6mo")
            
        st.write(f"DEBUG: Fetched {code}. Shape: {hist.shape}")
        # st.write(f"DEBUG: Columns: {hist.columns}")
        # st.write(f"DEBUG: Head: {hist.head(1)}")

        if hist.empty:
            st.error(f"DEBUG: {code} - History is EMPTY.")
            return None
            
        current_price = hist['Close'].iloc[-1]
        st.write(f"DEBUG: Current Price: {current_price}")
        
        st.write(f"DEBUG: {code} - Checkpoint A (MA)")
        
        # MA Calculation
        ma5 = hist['Close'].rolling(window=5).mean().iloc[-1]
        ma25 = hist['Close'].rolling(window=25).mean().iloc[-1]
        ma75 = hist['Close'].rolling(window=75).mean().iloc[-1]
        
        # Previous MA25 (5 days ago) for slope
        ma25_prev = hist['Close'].rolling(window=25).mean().iloc[-6]
        
        # ATR Calculation
        st.write(f"DEBUG: {code} - Checkpoint B (ATR)")
        try:
            high_low = hist['High'] - hist['Low']
            high_close = np.abs(hist['High'] - hist['Close'].shift())
            low_close = np.abs(hist['Low'] - hist['Close'].shift())
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(14).mean().iloc[-1]
        except Exception as e:
            st.error(f"ATR Calc Error: {e}")
            atr = 0

        # --- EXTENDED TECHNICAL ANALYSIS ---
        st.write(f"DEBUG: {code} - Checkpoint C (Technicals)")
        
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
            bb_pos = (current_price - bb_lower) / (bb_upper - bb_lower) 
            
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
            # kumo_bottom = min(senkou_a_val, senkou_b_val)

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

        except Exception as e:
            st.error(f"Technical Calc Error: {e}")
            return None

        # 3. Fundamentals
        st.write(f"DEBUG: {code} - Checkpoint D (Fundamentals)")
        pbr, per = 0, 0
        if fundamentals:
            pbr = fundamentals.get('pbr', 0)
            per = fundamentals.get('per', 0)

        commentary.append("")
        commentary.append(f"HV(ボラティリティ): {hv:.1f}%")
        commentary.append("※投資判断は自己責任で行ってください。")
        
        final_commentary = "\n".join(commentary)
        
        # Fix return dict to support both
        short_reason = []
        if score >= 80: short_reason.append("激アツ")
        elif score >= 60: short_reason.append("買い推奨")
        if vol_ratio > 1.5: short_reason.append("出来高急増")
        if rsi < 30: short_reason.append("RSI底打ち")
        if pbr < 1.0: short_reason.append("割安")
        
        return {
            "Code": code,
            "Price": current_price,
            "Score": score,
            "MA25": ma25,
            "Deviation": deviation,
            "RSI": rsi,
            "PBR": pbr,
            "PER": per,
            "Yield": 0,
            "RR": rr,
            "Details": "、".join(short_reason) if short_reason else "特になし",
            "AnalysisSummary": final_commentary
        }
    except Exception as e:
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
                # Convert timestamp (seconds) to date
                dt = datetime.fromtimestamp(ts)
                return dt.strftime('%Y-%m-%d')
        except:
            pass
            
        return "-"
    except:
        return "-"

def get_scored_stocks(status_callback=None):
    """
    Analyzes all tickers and returns sorted results.
    status_callback: function(float) to report progress (0.0 to 1.0)
    """
    results = []
    
    import streamlit as st
    
    # SEQUENTIAL EXECUTION FOR DEBUGGING
    results = []
    
    # DEBUG: Force UI output
    st.write(f"DEBUG: Starting analysis of {len(tickers)} tickers...")
    
    if not tickers:
        st.error("DEBUG: Tickers list is empty!")
        return []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_tickers = len(tickers)
    
    import time
    
    for i, code in enumerate(tickers):
        with st.container(): # Use container to isolate potential output errors
            try:
                status_text.text(f"Analyzing {code} ({i+1}/{total_tickers})...")
                
                # Sleep to be polite to API
                time.sleep(1.5)
                
                # Analyze synchronously
                res = analyze_stock(code)
                
                if res:
                    results.append(res)
                else:
                    st.write(f" -> Failed: {code} (No result)")
                    
            except Exception as e:
                st.error(f" -> Error analyzing {code}: {e}")
        
        progress_bar.progress((i + 1) / total_tickers)
        
        if status_callback:
            status_callback((i + 1) / total_tickers)
                
    # Sort by Score Descending
    results.sort(key=lambda x: x['Score'], reverse=True)
    st.write(f"DEBUG: Finished. Found {len(results)} valid stocks.")
    return results
                
    # Sort by Score Descending
    results.sort(key=lambda x: x['Score'], reverse=True)
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
