
import yfinance as yf
import pandas as pd
import numpy as np

def get_strategy_metrics(code):
    """
    Calculates swing trading metrics for a single stock code.
    Returns a dictionary or None if data is missing.
    """
    ticker = yf.Ticker(f"{code}.T")
    hist = ticker.history(period="6mo")
    
    if hist.empty:
        raise ValueError(f"No price data found for {code}.T (History is empty)")
        
    current_price = hist['Close'].iloc[-1]
    
    # Indicators
    # Indicators
    ma5 = hist['Close'].rolling(window=5).mean().iloc[-1]
    ma25 = hist['Close'].rolling(window=25).mean().iloc[-1]
    ma75 = hist['Close'].rolling(window=75).mean().iloc[-1]
    
    # RSI (for Entry Logic)
    delta = hist['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs)).iloc[-1]
    
    # Volatility (ATR 14)
    high_low = hist['High'] - hist['Low']
    high_close = np.abs(hist['High'] - hist['Close'].shift())
    low_close = np.abs(hist['Low'] - hist['Close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    
    # Recent High (Resistance) for Take Profit
    recent_high = hist['High'].iloc[-60:].max()
    
    # STRATEGY LOGIC (Dynamic)
    # STRATEGY LOGIC (Dynamic Entry)
    if current_price > ma5 and rsi >= 60:
        # Super Strong -> Don't wait, buy now
        entry_price = current_price
        dip_desc = "Momentum Buy (成行)"
    elif current_price > ma25 and rsi >= 45: # Slightly lowered threshold
        # Strong Trend -> Wait for slight dip
        entry_price = ma5
        dip_desc = "Trend Follow (MA5)"
    elif current_price > ma25:
        # Moderate -> Wait for deep dip
        entry_price = ma25
        dip_desc = "Dip Buy (MA25)"
    elif current_price > ma75:
        # Broken Trend -> Rebound aim
        entry_price = ma75
        dip_desc = "Rebound (MA75)"
    else:
        # Oversold
        entry_price = current_price
        dip_desc = "Bottom Fishing"
        
    stop_loss = entry_price - (2 * atr)
    
    target_profit = recent_high
    if (target_profit - entry_price) < (1.5 * atr):
            target_profit = entry_price + (4 * atr) # More room for trend logic
            
    # Risk Reward Calculation
    potential_profit = target_profit - entry_price
    potential_loss = entry_price - stop_loss
    rr_ratio = potential_profit / potential_loss if potential_loss > 0 else 0
    
    # Chart Data
    plot_data = hist[['Open', 'High', 'Low', 'Close']].reset_index()
    plot_data['MA5'] = hist['Close'].rolling(window=5).mean().values
    plot_data['MA25'] = hist['Close'].rolling(window=25).mean().values
    plot_data['MA75'] = hist['Close'].rolling(window=75).mean().values
    
    # --- Generate Text Report ---
    report_lines = []
    
    # 1. Fundamentals (Value)
    try:
        info = ticker.info
        per = info.get('trailingPE', None)
        pbr = info.get('priceToBook', None)
        div = info.get('dividendYield', None)
        
        fund_lines = []
        if per:
            fund_lines.append(f"PER: {per:.1f}倍")
        if pbr:
            fund_lines.append(f"PBR: {pbr:.2f}倍")
        if div:
            # Handle yfinance inconsistency (sometimes returns percentage, sometimes decimal)
            if div > 1.0:
                fund_lines.append(f"配当利回り: {div:.2f}%")
            else:
                fund_lines.append(f"配当利回り: {div*100:.2f}%")
            
        if fund_lines:
            report_lines.append(f"**【ファンダメンタルズ】**\n" + " / ".join(fund_lines))
            
            # Simple valuation comment
            if per and per < 15:
                report_lines.append("PERが15倍を下回っており、割安感があります。")
            elif per and per > 30:
                report_lines.append("PERが高いため、成長期待が高い反面、割高感もあります。")
            
            report_lines.append("※ 数値はYahoo Financeから取得していますが、株式分割等の影響で一時的に実態と乖離する場合があります。")
    except:
        pass # Ignore fundamental errors
    
    # 2. Trend Analysis
    if current_price > ma25 and ma25 > ma75:
        trend_str = "現在、株価は長期・中期移動平均線の上にあり、**理想的な上昇トレンド（パーフェクトオーダー）** を形成しています。"
    elif current_price < ma25 and ma25 < ma75:
            trend_str = "現在、株価は移動平均線を下回っており、**下落トレンド** の中にあります。逆張りには注意が必要です。"
    else:
            trend_str = "現在はトレンドが明確ではない、あるいはトレンド転換の過渡期にあります。"
            
    report_lines.append(f"\n**【トレンド分析】**\n{trend_str}")
    
    # 3. Strategy Explanation
    report_lines.append(f"\n**【戦略ポイント】**")
    if dip_desc == "Trend Follow (MA5)":
        report_lines.append(f"上昇モメンタムが強いため、**5日移動平均線（{int(ma5):,}円）付近** での浅い押し目を拾う「トレンドフォロー」を推奨します。置いていかれないよう積極的に狙う局面です。")
    elif dip_desc == "Dip Buy (MA25)":
        report_lines.append(f"過熱感がないため、**25日移動平均線（{int(ma25):,}円）付近** まで調整するのをじっくり待ちます。")
    elif dip_desc == "Rebound (MA75)":
        report_lines.append(f"25日線を割り込みましたが、**75日移動平均線（{int(ma75):,}円）** がサポートとして機能する可能性があります。")
    else:
        report_lines.append(f"明確なサポートラインが見当たらないため、直近安値を目処にします。")
            
    # 4. Risk Reward
    report_lines.append(f"\n**【リスク管理】**")
    report_lines.append(f"目標株価は直近高値の **{int(target_profit):,}円** に設定します。")
    report_lines.append(f"万が一読みが外れた場合は、**{int(stop_loss):,}円** で確実に損切りを行ってください。")
    report_lines.append(f"このトレードのリスクリワード比は **{rr_ratio:.2f}** です。（1.0以上で有利、2.0以上で推奨）")
    
    detailed_report = "\n".join(report_lines)

    return {
        "Code": code,
        "CurrentPrice": current_price,
        "EntryPrice": entry_price,
        "DipDesc": dip_desc,
        "StopLoss": stop_loss,
        "TargetProfit": target_profit,
        "RR": rr_ratio,
        "ATR": atr,
        "DetailedReport": detailed_report,
        "PlotData": plot_data
    }

import yfinance as yf
import pandas as pd
import numpy as np

def get_market_trend():
    """
    Analyzes the Nikkei 225 index (^N225) to determine the overall market trend.
    Returns a dictionary with trend status and color.
    """
    try:
        ticker = yf.Ticker("^N225")
        hist = ticker.history(period="3mo")
        
        if hist.empty:
            return {"status": "取得失敗", "color": "gray", "price": 0, "change": 0}
            
        current_price = hist['Close'].iloc[-1]
        prev_price = hist['Close'].iloc[-2]
        change = current_price - prev_price
        
        ma5 = hist['Close'].rolling(window=5).mean().iloc[-1]
        ma25 = hist['Close'].rolling(window=25).mean().iloc[-1]
        
        # Trend Logic
        if current_price > ma25:
            if ma5 > ma25:
                status = "上昇トレンド (強)"
                color = "red" # Japanese style: Red = Up
            else:
                status = "上昇トレンド (調整局面)"
                color = "orange"
        elif current_price < ma25:
            if ma5 < ma25:
                status = "下落トレンド (弱)"
                color = "green" # Japanese style: Green = Down
            else:
                status = "下落トレンド (反発局面)"
                color = "blue"
        else:
            status = "トレンド不明"
            color = "gray"
            
        return {
            "status": status,
            "color": color,
            "price": current_price,
            "change": change
        }
    except Exception as e:
        return {"status": "エラー", "color": "gray", "price": 0, "change": 0}

def calculate_strategy():
    targets = [
        "1925", # Daiwa House (Rank 1, Earnings 2/13)
        "6770", # Alps Alpine (Rank 3, Earnings 4/30)
        "5101", # Yokohama Rubber (Rank 8, Earnings Safe)
        "8630", # SOMPO (Rank 9, Earnings 2/13)
    ]
    
    print("| Stock | Current Price | Entry Target (Dip) | Stop Loss (Loss Cut) | Take Profit (Rikaku) | R/R Ratio |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- |")
    
    for code in targets:
        data = get_strategy_metrics(code)
        
        if not data:
             print(f"| {code} | N/A | N/A | N/A | N/A | N/A |")
             continue
        
        # Formatting
        fmt_current = f"{data['CurrentPrice']:,.0f}"
        fmt_entry = f"{data['EntryPrice']:,.0f}"
        fmt_stop = f"{data['StopLoss']:,.0f}"
        fmt_take = f"{data['TargetProfit']:,.0f}"
        fmt_rr = f"{data['RR']:.2f}"
        dip_desc = data['DipDesc']
        
        print(f"| {data['Code']} | {fmt_current} | **{fmt_entry}** <br>({dip_desc}) | {fmt_stop} | {fmt_take} | {fmt_rr} |")

if __name__ == "__main__":
    calculate_strategy()
