
import yfinance as yf
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# Partial List of Nikkei 225 Components (Major ones gathered)
tickers = [
    "7203", "8306", "9984", "6501", "6758", "8316", "8035", "9983", "6857", "8411",
    "1332", "4061", "5714", "7011", "8604", "4063", "7012", "1605", "4151", "5801",
    "7013", "8630", "1721", "4183", "5802", "7201", "8725", "1801", "4188", "5803",
    "7202", "8801", "1802", "4208", "8750", "1803", "6103", "7205", "8766", "1812",
    "4324", "6113", "7211", "8795", "1925", "4452", "6301", "7261", "8802", "1928",
    "4502", "6302", "7267", "8804", "1963", "4503", "6305", "7269", "2002", "4506",
    "6326", "7270", "8830", "2269", "4507", "6361", "7731", "9001", "2282", "4519",
    "7733", "9005", "2501", "4523", "6367", "7735", "9007", "2502", "4543", "6471",
    "7751", "9008", "2503", "4568", "6472", "7752", "9009", "2531", "4689", "6473",
    "7762", "9020", "2768", "4704", "6479", "7911", "9021", "2801", "4901", "7912",
    "9022", "2802", "4902", "7951", "9147", "2871", "4911", "6503", "8001", "9064",
    "2914", "6504", "8002", "3086", "5020", "6506", "8015", "3099", "5101", "4578",
    "9101", "9104", "9107", "3382", "3401", "3402", "3405", "3407", "3436", "4004",
    "4005", "4021", "4042", "4043", "4061", "4063", "4183", "4208", "4452", "4502",
    "4503", "4506", "4507", "4519", "4523", "4543", "4568", "4578", "4661", "4689",
    "4704", "4751", "4755", "4901", "4911", "5019", "5020", "5108", "5201", "5214",
    "5232", "5233", "5301", "5332", "5333", "5401", "5406", "5411", "5631", "5703",
    "5706", "5711", "5713", "5714", "5801", "5802", "5803", "5831", "6098", "6103",
    "6113", "6178", "6301", "6302", "6305", "6326", "6361", "6367", "6471", "6472",
    "6473", "6479", "6501", "6503", "6504", "6506", "6594", "6645", "6701", "6702",
    "6723", "6724", "6752", "6753", "6758", "6762", "6770", "6841", "6857", "6861",
    "6902", "6920", "6952", "6954", "6971", "6976", "6981", "6988", "7004", "7011",
    "7012", "7013", "7186", "7201", "7202", "7203", "7205", "7261", "7267", "7269",
    "7270", "7272", "7731", "7733", "7735", "7741", "7751", "7752", "7762", "7832",
    "7911", "7912", "7951", "7974", "8001", "8002", "8015", "8031", "8035", "8053",
    "8058", "8233", "8252", "8253", "8267", "8304", "8306", "8308", "8309", "8316",
    "8331", "8354", "8411", "8591", "8601", "8604", "8630", "8697", "8725", "8750",
    "8766", "8795", "8801", "8802", "8804", "8830", "9001", "9005", "9007", "9008",
    "9009", "9020", "9021", "9022", "9064", "9101", "9104", "9107", "9147", "9201",
    "9202", "9301", "9432", "9433", "9434", "9501", "9502", "9503", "9531", "9532",
    "9602", "9735", "9766", "9843", "9983", "9984"
]
tickers = list(set(tickers)) # Deduplicate just in case

def analyze_stock(code):
    try:
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
        
        # 3. Fundamentals (Fetch only if trend is somewhat okay to save time? No, fetch all for now)
        try:
            info = ticker.info
            pbr = info.get('priceToBook', 0)
            per = info.get('trailingPE', 0)
            dividend_yield = info.get('dividendYield', 0)
            if dividend_yield is None: dividend_yield = 0
            
            # Normalize yield to percentage
            # Some sources return 0.03, others 3.0. Assume < 0.3 (30%) is decimal.
            if dividend_yield < 0.3: 
                dividend_yield *= 100
        except:
            pbr = 0
            per = 0
            dividend_yield = 0

        # --- SCORING LOGIC (Total Max ~100) ---
        score = 0.0
        details = []
        
        # 1. Trend (Max 35)
        if current_price > ma25:
            score += 10
            if ma25 > ma75:
                score += 10
                if ma5 > ma25:
                    score += 5
                    details.append("上昇トレンド(強)")
                else:
                    details.append("上昇トレンド継続")
            else:
                details.append("短期上昇中")
        
        # Slope (Max 10)
        slope = (ma25 - ma25_prev) / ma25_prev * 100
        if slope > 0:
            score += min(10, slope * 10)

        # 2. Pullback & RSI (Max 25)
        # Deviation Score
        deviation = (current_price - ma25) / ma25 * 100
        if current_price > ma25 and -2.0 <= deviation <= 4.0:
            # Closer to 0-1% deviation is better
            dist = abs(deviation - 0.5)
            pullback_score = max(0, 15 - (dist * 5))
            score += pullback_score
            if pullback_score > 10: details.append("押し目")

        # RSI Score (Buy the dip in uptrend)
        if 30 <= rsi <= 45:
            score += 10
            details.append(f"RSI売られすぎ({rsi:.0f})")
        elif 45 < rsi <= 60:
            score += 5
        elif rsi >= 75:
            score -= 5 # Overbought warning
            details.append(f"RSI過熱気味({rsi:.0f})")

        # 3. Volume (Max 10)
        if vol_ratio >= 2.0:
            score += 10
            details.append("出来高急増")
        elif vol_ratio >= 1.3:
            score += 5

        # 4. Fundamentals (Max 15)
        # PBR (Value)
        if 0 < pbr < 1.0:
            score += 5
            details.append(f"PBR割安({pbr:.2f})")
        
        # PER (Safety/Value)
        if 0 < per < 15.0:
            score += 5
            
        # Yield
        if dividend_yield >= 3.5:
            score += 5
            details.append(f"高配当({dividend_yield:.1f}%)")

        # 5. Risk / Reward (Max 15)
        # ... (Existing RR logic)
        recent_high = hist['High'].iloc[-60:].max()
        StopLoss = ma25 - atr # Generic support stop
        if current_price < ma25: StopLoss = current_price - 2*atr
        
        upside = recent_high - current_price
        downside = current_price - StopLoss
        if downside <= 0: downside = 0.1 
        
        rr = upside / downside
        if rr >= 1.0:
            rr_score = min(15, rr * 5)
            score += rr_score
            if rr > 2.5:
                details.append(f"R/R良({rr:.1f})")
        
        score = int(score)
        
        return {
            "Code": code,
            "Price": current_price,
            "Score": score,
            "MA25": ma25,
            "Deviation": deviation,
            "RSI": rsi,
            "PBR": pbr,
            "PER": per,
            "Yield": dividend_yield,
            "RR": rr,
            "Details": "、".join(details)
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
    
    # Use ThreadPool to speed up
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(analyze_stock, code) for code in tickers]
        total_futures = len(futures)
        
        for i, future in enumerate(futures):
            res = future.result()
            if res:
                results.append(res)
            
            if status_callback:
                status_callback((i + 1) / total_futures)
                
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
