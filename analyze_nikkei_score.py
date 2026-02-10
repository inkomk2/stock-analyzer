
import requests

# ... (Previous imports)
import yfinance as yf
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# Partial List of Nikkei 225 Components (Major ones gathered)
tickers = [
    # ... (Keep tickers list)
]
tickers = list(set(tickers)) # Deduplicate just in case
# LIMIT TO TOP 50 for Cloud Stability
tickers = tickers[:50]

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
        high_low = hist['High'] - hist['Low']
        high_close = np.abs(hist['High'] - hist['Close'].shift())
        low_close = np.abs(hist['Low'] - hist['Close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]

        # --- EXTENDED TECHNICAL ANALYSIS ---
        
        # 1. MACD (12, 26, 9)
        ema12 = hist['Close'].ewm(span=12, adjust=False).mean()
        ema26 = hist['Close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        # hist_macd = macd - signal
        macd_val = macd.iloc[-1]
        signal_val = signal.iloc[-1]
        
        # 2. Bollinger Bands (20, 2sigma)
        ma20 = hist['Close'].rolling(window=20).mean()
        std20 = hist['Close'].rolling(window=20).std()
        bb_upper = ma20 + (2 * std20)
        bb_lower = ma20 - (2 * std20)
        # bb_width = (bb_upper - bb_lower) / ma20
        bb_pos = (current_price - bb_lower) / (bb_upper - bb_lower) # 0=Lower, 0.5=Mid, 1=Upper
        
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

        # 8. Historical Volatility (HV) - 20 days annualized
        ln_ret = np.log(hist['Close'] / hist['Close'].shift(1))
        hv = ln_ret.rolling(window=20).std().iloc[-1] * np.sqrt(250) * 100

        # --- NEW METRICS ---
        # 1. RSI (14)
        delta = hist['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs)).iloc[-1]
        
        # 2. Volume Spike
        vol_ma25 = hist['Volume'].rolling(window=25).mean().iloc[-1]
        current_vol = hist['Volume'].iloc[-1]
        vol_ratio = current_vol / vol_ma25 if vol_ma25 > 0 else 1.0
        
        # 3. Fundamentals
        pbr, per = 0, 0
        if fundamentals:
            pbr = fundamentals.get('pbr', 0)
            per = fundamentals.get('per', 0)
        elif ticker:
            # Single mode fallback
            try:
                info = ticker.info
                pbr = info.get('priceToBook', 0)
                per = info.get('trailingPE', 0)
            except:
                 pbr, per = 0, 0

        # --- SCORING LOGIC (Enhanced) ---
        score = 0
        
        # Trend (MA + Ichimoku + MACD)
        if current_price > ma25: score += 10 # Base Trend
        if ma5 > ma25: score += 5 # Strong Momentum
        if current_price > kumo_top: score += 5 # Above Cloud
        if tenkan_val > kijun_val: score += 5 # Tenkan/Kijun Cross
        if macd_val > signal_val: score += 5 # MACD Bullish
        if macd_val > 0: score += 5 # MACD Positive
        
        # Momentum & Volatility
        if 30 <= rsi <= 50: score += 10 # Good entry zone
        elif rsi > 75: score -= 5 # Overbought
        
        if score < 50 and bb_pos < 0.1: score += 10 # Bollinger bounce buy
        
        # Volume
        if vol_ratio > 2.0: score += 5 # Big Volume

        # Fundamentals fallback
        try:
            info = ticker.info
            pbr = info.get('priceToBook', 0)
            per = info.get('trailingPE', 0)
        except:
             pbr, per = 0, 0

        # Fundamental Score (Yield Removed)
        if 0 < pbr < 1.0: score += 5
        if 0 < per < 15: score += 5
        
        # Risk Reward (Re-integrated)
        recent_high = hist['High'].iloc[-60:].max()
        StopLoss = ma25 - atr 
        if current_price < ma25: StopLoss = current_price - 2*atr
        
        upside = recent_high - current_price
        downside = current_price - StopLoss
        if downside <= 0: downside = 0.1 
        
        rr = upside / downside
        if rr >= 1.0:
            score += min(15, rr * 5)
        if rr >= 1.0:
            rr_score = min(15, rr * 5)
            score += rr_score
            if rr > 2.5:
                details.append(f"R/R良({rr:.1f})")
        
        score = int(score)
        
        # Cap score
        score = min(100, int(score))

        # --- COMMENTARY GENERATION (Approx 20 lines) ---
        commentary = []
        commentary.append(f"【総合評価】 スコア: {score}点")
        commentary.append(f"現在値: {current_price:,.0f}円 (前日比 {(current_price - hist['Close'].iloc[-2]):+,.0f}円)")
        
        # Trend
        trend_desc = "上昇" if current_price > ma25 else "下落"
        cloud_desc = "雲上" if current_price > kumo_top else ("雲下" if current_price < kumo_bottom else "雲中")
        commentary.append(f"トレンド: {trend_desc}トレンド / 一目均衡表: {cloud_desc}")
        
        # MACD
        macd_val = float(macd_val) if not np.isnan(macd_val) else 0.0
        signal_val = float(signal_val) if not np.isnan(signal_val) else 0.0
        macd_desc = "ゴールデンクロス中" if macd_val > signal_val else "デッドクロス中"
        commentary.append(f"MACD: {macd_desc} (MACD:{macd_val:.1f} / Signal:{signal_val:.1f})")
        
        # Bollinger
        bb_desc = "バンド内に収束"
        if bb_pos > 1.0: bb_desc = "+2σ突破 (過熱感あり)"
        elif bb_pos < 0.0: bb_desc = "-2σ割れ (売られすぎ)"
        commentary.append(f"ボリンジャーバンド: {bb_desc}")
        
        # RSI & Volume
        commentary.append(f"RSI(14): {rsi:.1f} ({'過熱圏' if rsi>70 else ('売られすぎ' if rsi<30 else '中立')})")
        commentary.append(f"出来高: 通常比 {vol_ratio:.1f}倍 ({'急増' if vol_ratio>1.5 else '通常'})")
        
        # Fundamentals
        commentary.append(f"PBR: {pbr:.2f}倍 / PER: {per:.1f}倍")
        
        # Strategy
        commentary.append("")
        commentary.append("【AI売買判断】")
        if score >= 80:
             commentary.append("評価: ★★★★★ (激アツ)")
             commentary.append("テクニカル・ファンダメンタルズ共に死角なし。")
             commentary.append("積極的なエントリーを推奨します。")
        elif score >= 60:
             commentary.append("評価: ★★★★☆ (買い推奨)")
             commentary.append("上昇トレンドを維持しており、押し目買いの好機。")
             commentary.append("MACDや一目均衡表も好転しています。")
        elif score >= 40:
             commentary.append("評価: ★★★☆☆ (様子見)")
             commentary.append("悪くはありませんが、決定打に欠けます。")
             commentary.append("トレンドが明確になるまで待機を推奨。")
        else:
             commentary.append("評価: ★★☆☆☆ (危険)")
             commentary.append("下落トレンド、または過熱感が強すぎます。")
             commentary.append("今は手出し無用です。")
             
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
    
    # SEQUENTIAL EXECUTION FOR DEBUGGING
    # The user reports "No Data" even with ThreadPool.
    # We need to see EXACTLY what happens.
    
    print("Starting SEQUENTIAL analysis (for debugging)...")
    total_tickers = len(tickers)
    
    for i, code in enumerate(tickers):
        try:
            print(f"[{i+1}/{total_tickers}] Analyzing {code}...")
            
            # Analyze synchronously
            res = analyze_stock(code)
            
            if res:
                results.append(res)
                print(f" -> Success: Score={res['Score']}")
            else:
                print(f" -> Failed: No result returned")
                
        except Exception as e:
            print(f" -> Error analyzing {code}: {e}")
        
        if status_callback:
            status_callback((i + 1) / total_tickers)
                
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
