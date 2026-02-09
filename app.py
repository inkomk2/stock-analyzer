import streamlit as st
import sys
import traceback

# --- Global Error Handler ---
def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    st.error("アプリケーションエラーが発生しました")
    st.code("".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))

sys.excepthook = handle_exception

# --- Imports ---

import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
from analyze_nikkei_score import get_scored_stocks, get_next_earnings_date, analyze_stock
from calculate_swing_strategy import get_strategy_metrics

from concurrent.futures import ThreadPoolExecutor

# Page Config
st.set_page_config(page_title="Stock Analyzer", page_icon="📈", layout="wide")

# Custom CSS for Mobile
st.markdown("""
<style>
    .stButton>button {
        width: 100%;
        border-radius: 20px;
        height: 3em;
        font-weight: bold;
    }
    .metric-card {
        background-color: #1e1e1e;
        padding: 10px;
        border-radius: 10px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.5);
    }
    h1, h2, h3 {
        font-family: "Meiryo", sans-serif;
    }
</style>
""", unsafe_allow_html=True)

st.title("📈 Stock Analyzer")

# --- Helper Function for Name Fetching ---
@st.cache_data(ttl=86400) # Cache names for 24 hours
def load_name_map():
    import json
    try:
        with open("nikkei_names.json", "r", encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def get_stock_name(code):
    name_map = load_name_map()
    if code in name_map:
        return name_map[code]
        
    try:
        t = yf.Ticker(f"{code}.T")
        # Try shortName first, then longName
        return t.info.get('shortName') or t.info.get('longName') or code
    except:
        return code

# --- Helper for Score Fetching ---
@st.cache_data(ttl=3600) # Cache for 1 hour
def load_ranking_data():
    return get_scored_stocks()

# --- Helper Function for Analysis Rendering ---
def render_analysis_view(code_input):
    """Renders the analysis view for a given code."""
    try:
        metrics = get_strategy_metrics(code_input)
        name = get_stock_name(code_input)
        
        if metrics:
            # --- Fetch Score ---
            param_score = "-"
            try:
                scores = load_ranking_data()
                for row in scores:
                    if row['Code'] == str(code_input):
                        param_score = row['Score']
                        break
            except:
                pass
            
            # Fallback: Calculate on the fly if not found (e.g. non-Nikkei225)
            if param_score == "-":
                try:
                    score_data = analyze_stock(code_input)
                    if score_data:
                        param_score = score_data['Score']
                except:
                    pass
            
            # --- Header & Score ---
            st.subheader(f"{name} ({code_input})")
            st.metric("総合スコア", f"{param_score}点", help="トレンド・過熱感・リスクリワードから算出した、AIによる推奨度です。")
            
            # --- Metrics (Reordered) ---
            # Row 1: Price & Entry
            c1, c2 = st.columns(2)
            with c1:
                st.metric("現在値", f"¥{metrics['CurrentPrice']:,.0f}")
            with c2:
                st.metric("エントリー目安", f"¥{metrics['EntryPrice']:,.0f}", delta=f"{metrics['EntryPrice']-metrics['CurrentPrice']:,.0f}", delta_color="inverse")
            
            # Row 2: Target & Stop
            c3, c4 = st.columns(2)
            with c3:
                st.metric("利確目標", f"¥{metrics['TargetProfit']:,.0f}", delta=f"{metrics['TargetProfit']-metrics['CurrentPrice']:,.0f}")
            with c4:
                st.metric("損切りライン", f"¥{metrics['StopLoss']:,.0f}", delta_color="off")

            # Strategy Badge
            st.info(f"戦略: **{metrics['DipDesc']}** | リスクリワード比: **{metrics['RR']:.2f}**")
            
            # --- CHART ---
            st.subheader("3ヶ月チャート")
            
            # Slice to last 3 months (approx 75 records)
            plot_data = metrics['PlotData'].tail(75)
            
            fig = go.Figure()

            # Candlestick
            fig.add_trace(go.Candlestick(
                x=plot_data['Date'],
                open=plot_data['Open'],
                high=plot_data['High'],
                low=plot_data['Low'],
                close=plot_data['Close'],
                name=name,
                increasing_line_color='#ff4b4b', # Red for Up
                decreasing_line_color='#00b894'  # Green for Down
            ))
            
            # Moving Averages
            fig.add_trace(go.Scatter(x=plot_data['Date'], y=plot_data['MA5'], line=dict(color='white', width=1), name='MA5'))
            fig.add_trace(go.Scatter(x=plot_data['Date'], y=plot_data['MA25'], line=dict(color='#ff9f43', width=1.5), name='MA25'))
            fig.add_trace(go.Scatter(x=plot_data['Date'], y=plot_data['MA75'], line=dict(color='#54a0ff', width=1.5), name='MA75'))

            # Entry/Stop lines
            fig.add_hline(y=metrics['EntryPrice'], line_dash="dash", line_color="green", annotation_text="Entry")
            fig.add_hline(y=metrics['StopLoss'], line_dash="dot", line_color="red", annotation_text="Stop")
            fig.add_hline(y=metrics['TargetProfit'], line_dash="dash", line_color="blue", annotation_text="Target")

            # Layout similar to "Photo"
            fig.update_layout(
                xaxis_rangeslider_visible=False, 
                height=400, 
                distribute_legend=True, # Custom flag? No, standard plot settings
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                ),
                margin=dict(l=0, r=0, t=30, b=0),
                template="plotly_dark",
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # --- REPORT ---
            st.markdown("---")
            st.subheader("📝 Analysis Report")
            st.markdown(metrics['DetailedReport'])
            
        else:
            st.error(f"データを取得できませんでした。コードを確認してください。")
    except Exception as e:
        st.error(f"エラーが発生しました: {e}")

# --- Helper for Earnings ---
@st.cache_data(ttl=3600)
def fetch_earnings_map(codes):
    """Fetches earnings dates in parallel for a list of codes."""
    earnings_map = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_code = {executor.submit(get_next_earnings_date, code): code for code in codes}
        for future in future_to_code:
            code = future_to_code[future]
            try:
                earnings_map[code] = future.result()
            except:
                earnings_map[code] = "-"
    return earnings_map

# --- Initialize Session State for Drill-down ---
if 'ranking_target' not in st.session_state:
    st.session_state.ranking_target = None

# --- Main Layout (Tabs) ---
tab1, tab2, tab3 = st.tabs(["📊 ランキング", "🔍 詳細分析", "⚙️ 設定"])

# --- TAB 1: RANKING ---
with tab1:
    # Drill-down View
    if st.session_state.ranking_target:
        if st.button("⬅️ ランキングに戻る"):
            st.session_state.ranking_target = None
            st.rerun()
            
        render_analysis_view(st.session_state.ranking_target)
        
    # List View (Normal)
    else:
        st.header("日経225 スコアランキング")
        
        if st.button("🔄 データを更新"):
            st.cache_data.clear()
            st.rerun()
            


        try:
            with st.spinner("市場データを分析中..."):
                scores = load_ranking_data()
                
            # Fixed top 20
            top_n = 20
            
            displayed_scores = scores[:top_n]
            target_codes = [row['Code'] for row in displayed_scores]
            
            with st.spinner("決算発表日を取得中..."):
                earnings_map = fetch_earnings_map(target_codes)
            
            # Prepare dataframe for display
            display_data = []
            for row in displayed_scores:
                name = get_stock_name(row['Code'])
                earnings = earnings_map.get(row['Code'], '-')
                
                # Short earnings date for mobile (e.g. 2026-02-03 -> 02/03)
                short_earnings = earnings
                if len(earnings) >= 10:
                    short_earnings = earnings[5:].replace('-', '/')
                
                display_data.append({
                    '順位': displayed_scores.index(row) + 1, 
                    'コード': row['Code'],
                    '銘柄': f"{name} ({row['Code']})",
                    'スコア': row['Score'],
                    '現在値': f"¥{row['Price']:,.0f}", 
                    '乖離率': f"{row['Deviation']:.1f}%",
                    '決算発表': earnings,
                    '決算日(短)': short_earnings, # For mobile
                    'R/R': f"{row['RR']:.2f}",
                    '選定理由': row['Details']
                })
                
            df_display = pd.DataFrame(display_data)
            
            # Mobile Toggle
            mobile_mode = st.toggle("スマホ表示（省スペース）", value=True)
            
            st.caption("👇 **行をタップすると詳細分析が表示されます**")
            
            if mobile_mode:
                # Compact Column Config for Mobile
                # Columns: Rank, Name(with Code), Score, Price, Earnings(Short)
                event = st.dataframe(
                    df_display[["順位", "銘柄", "スコア", "現在値", "決算日(短)"]], # Score moved before Price
                    column_config={
                        "順位": st.column_config.NumberColumn("#", width="small"), # Renamed to #
                        "銘柄": st.column_config.TextColumn("銘柄", width="medium"),
                        "スコア": st.column_config.NumberColumn("点数", format="%d", width="small"), 
                        "現在値": st.column_config.TextColumn("株価", width="small"),
                        "決算日(短)": st.column_config.TextColumn("決算", width="small"),
                    },
                    use_container_width=True,
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="single-row"
                )
            else:
                # Full Column Config
                event = st.dataframe(
                    df_display,
                    column_config={
                        "順位": st.column_config.NumberColumn("順位", width="small"),
                        "コード": st.column_config.TextColumn("コード", width="small"),
                        "銘柄": st.column_config.TextColumn("銘柄", width="medium"),
                        "スコア": st.column_config.ProgressColumn("スコア", min_value=0, max_value=100, format="%d点"),
                        "決算発表": st.column_config.TextColumn("決算発表", width="medium"),
                        "R/R": st.column_config.TextColumn("R/R", width="small"),
                        "選定理由": st.column_config.TextColumn("選定理由", width="large"),
                    },
                    use_container_width=True,
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="single-row"
                )
            
            # Handle Selection
            if len(event.selection.rows) > 0:
                selected_index = event.selection.rows[0]
                selected_row = df_display.iloc[selected_index]
                target_code = selected_row['コード']
                
                # Set session state and rerun to show drill-down
                st.session_state.ranking_target = target_code
                st.rerun()

            st.caption("※ スコアはトレンド・過熱感・リスクリワードから算出されています。")
                
            with st.expander("ℹ️ スコアの見方・目安"):
                st.markdown("""
                - **80点以上 (激アツ)**: 
                    上昇トレンド・押し目・リスクリワードの全てが完璧な状態。**強気にエントリー**を検討できる水準です。
                - **60点〜79点 (買い推奨)**: 
                    多くの条件が揃っています。チャートを見てタイミングが合えばエントリー推奨。
                - **40点〜59点 (様子見)**: 
                    悪くはないですが、何か一つ（トレンドが弱い、少し高値圏など）懸念があります。
                - **40点未満**: 
                    現在はエントリーに適していません。
                """)
            
        except Exception as e:
            st.error(f"データ読み込みエラー: {e}")

# --- TAB 2: ANALYZER ---
with tab2:
    st.header("銘柄詳細分析")
    
    default_code = "9984"
    code_input = st.text_input("銘柄コードを入力 (例: 9984)", default_code)
    
    if st.button("分析開始"):
        with st.spinner(f"{code_input} を詳細分析中..."):
            render_analysis_view(code_input)

# --- TAB 3: SETUP ---
with tab3:
    st.header("モバイルアクセスの手順")
    st.markdown("""
    1.  **ngrokの起動**: 
        アプリ起動時に表示された黒い画面にURLが表示されています。
    2.  **スマホでアクセス**: 
        URL (`https://....ngrok-free.app`) をコピーして、スマホのブラウザで開いてください。
    """)
