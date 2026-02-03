
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
        
        # Scoring Logic (Max 100, Fine-grained)
        score = 0.0
        details = []
        
        # 1. Trend Strength (Max 40)
        # Base trend score
        if current_price > ma25:
            score += 10
            if ma25 > ma75:
                score += 10
                # Perfect Order Bonus
                if ma5 > ma25:
                    score += 5
                    details.append("上昇トレンド(強)")
                else:
                    details.append("上昇トレンド継続")
            else:
                details.append("短期上昇中")
                
        # Slope check (Max 15)
        # Calculate slope as % change of MA25 over 5 days
        slope = (ma25 - ma25_prev) / ma25_prev * 100
        if slope > 0:
            # e.g. 0.5% slope = 5 pts, 1.0% = 10 pts, max 15
            slope_score = min(15, slope * 10)
            score += slope_score
        
        # 2. Buying Opportunity (Pullback) (Max 30)
        # Ideal deviation is around +1% to +3% (Strong trend pullback)
        # Or -1% to +1% (Deep pullback)
        deviation = (current_price - ma25) / ma25 * 100
        
        pullback_score = 0
        if -3.0 <= deviation <= 5.0:
            # Create a bell curve peak around 1.0%
            dist = abs(deviation - 1.0)
            # Max 30 points if deviation is exactly 1.0%
            # Lose 5 points for every 1% distance
            pullback_score = max(0, 30 - (dist * 7))
            
            if pullback_score > 20:
                details.append("絶好の押し目")
            elif pullback_score > 10:
                details.append("買いゾーン")
        
        score += pullback_score

        # 3. Risk / Reward Potential (Max 30)
        # Recent High
        recent_high = hist['High'].iloc[-60:].max()
        StopLoss = ma25 - atr # Generic support stop
        if current_price < ma25: StopLoss = current_price - 2*atr
        
        upside = recent_high - current_price
        downside = current_price - StopLoss
        if downside <= 0: downside = 0.1 # Prevent div by zero
        
        rr = upside / downside
        
        # Max 30 points. RR 3.0 = 30 pts. RR 1.0 = 5 pts.
        if rr >= 1.0:
            rr_score = min(30, rr * 8)
            score += rr_score
            if rr > 2.5:
                details.append(f"R/R優秀({rr:.1f})")
        
        # Final integer score
        score = int(score)
        
        return {
            "Code": code,
            "Price": current_price,
            "Score": score,
            "MA25": ma25,
            "Deviation": deviation,
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
