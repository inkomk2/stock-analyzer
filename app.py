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
from calculate_swing_strategy import get_strategy_metrics, get_market_trend

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

# --- Market Overview ---
try:
    with st.spinner("市場環境を確認中..."):
        market = get_market_trend()
        
    m_color = market['color']
    m_status = market['status']
    m_price = market['price']
    m_change = market['change']
    
    # Custom HTML Banner
    if m_status != "エラー":
        banner_color = {
            "red": "#ff4b4b",
            "orange": "#ff9f43",
            "green": "#00b894",
            "blue": "#54a0ff",
            "gray": "#636e72"
        }.get(m_color, "#636e72")
        
        st.markdown(f"""
        <div style="background-color: {banner_color}; padding: 10px; border-radius: 5px; margin-bottom: 20px; color: white;">
            <h3 style="margin: 0; padding: 0;">日経平均: {m_price:,.0f}円 ({m_change:+,.0f})</h3>
            <p style="margin: 0; padding: 0; font-weight: bold;">市場環境: {m_status}</p>
        </div>
        """, unsafe_allow_html=True)
except:
    pass

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

# --- Helper Function for Ranking Rendering ---
def render_ranking_view(scored_stocks):
    st.header("🏆 AIスコアランキング")
    
    if not scored_stocks:
        st.info("データがありません。分析を実行してください。")
        return

    # Mobile Toggle
    mobile_mode = st.toggle("スマホ表示（省スペース）", value=True)

    # Create Tabs
    tab1, tab2 = st.tabs(["📈 スイング (本命)", "🚀 短期急騰 (デイ/スキャ)"])
    
    # --- TAB 1: SWING (Main) ---
    with tab1:
        st.caption("※トレンドとモメンタムのバランスを重視した、数日〜数週間向けのランキング")
        # Sort by Swing Score
        swing_stocks = sorted(scored_stocks, key=lambda x: x['Score'], reverse=True)
        
        rank_data = []
        for i, s in enumerate(swing_stocks):
            # Check for earnings within 14 days
            earnings_date = get_next_earnings_date(s['Code'])
            note = ""
            if earnings_date:
                from datetime import datetime
                try:
                    ed = datetime.strptime(earnings_date, "%Y-%m-%d")
                    days_left = (ed - datetime.now()).days
                    if 0 <= days_left <= 14:
                        note = f"⚠️決算 {days_left}日後"
                except:
                    pass
            
            rank_data.append({
                "順位": i + 1,
                "コード": s['Code'],
                "銘柄": f"{get_stock_name(s['Code'])}",
                "現在値": f"{s['Price']:,.0f}",
                "スコア": s['Score'],
                "トレンド": "上昇" if s['MA25'] < s['Price'] else "下降",
                "R/R": f"{s['RR']:.2f}",
                "決算": note,
                "選定理由": s.get('Details', '')
            })
            
        df = pd.DataFrame(rank_data)

        # Column Config
        if mobile_mode:
            cols = ["順位", "銘柄", "スコア", "現在値", "決算"]
            cfg = {
                "順位": st.column_config.NumberColumn("#", width="small"),
                "銘柄": st.column_config.TextColumn("銘柄", width="medium"),
                "スコア": st.column_config.NumberColumn("点数", format="%d", width="small"),
                "現在値": st.column_config.TextColumn("株価", width="small"),
                "決算": st.column_config.TextColumn("決算", width="small"),
            }
        else:
            cols = ["順位", "コード", "銘柄", "スコア", "現在値", "トレンド", "R/R", "決算", "選定理由"]
            cfg = {
                "順位": st.column_config.NumberColumn("Rank", width="small"),
                "スコア": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
            }

        event = st.dataframe(
            df[cols],
            column_config=cfg,
            height=600,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="df_swing"
        )

        if len(event.selection.rows) > 0:
            row_idx = event.selection.rows[0]
            target_code = df.iloc[row_idx]['コード']
            st.session_state.ranking_target = target_code
            st.rerun()

    # --- TAB 2: SHORT-TERM (Burst) ---
    with tab2:
        st.caption("※3日間の急騰、出来高急増、ローソク足の強さを重視した「今」動いている銘柄")
        
        # Sort by ScoreShort
        short_stocks = [s for s in scored_stocks if s.get('ScoreShort', 0) > 0]
        short_stocks.sort(key=lambda x: x.get('ScoreShort', 0), reverse=True)
        
        rank_short = []
        for i, s in enumerate(short_stocks[:50]): # Top 50 limit
            # Check for earnings
            earnings_date = get_next_earnings_date(s['Code'])
            note = ""
            if earnings_date:
                from datetime import datetime
                try:
                    ed = datetime.strptime(earnings_date, "%Y-%m-%d")
                    days_left = (ed - datetime.now()).days
                    if 0 <= days_left <= 14:
                        note = f"⚠️{days_left}日後"
                    elif 15 <= days_left <= 30:
                        note = f"{days_left}日後"
                except:
                    pass

            rank_short.append({
                "順位": i + 1,
                "コード": s['Code'],
                "銘柄": f"{get_stock_name(s['Code'])}",
                "現在値": f"{s['Price']:,.0f}",
                "短期スコア": s.get('ScoreShort', 0),
                "決算": note,
                "急騰要因": s.get('Details', '特になし')
            })
            
        df_short = pd.DataFrame(rank_short)
        
        # Column Config for Short Term
        if mobile_mode:
            cols_short = ["順位", "銘柄", "短期スコア", "現在値", "決算", "急騰要因"]
            cfg_short = {
                "順位": st.column_config.NumberColumn("#", width="small"),
                "銘柄": st.column_config.TextColumn("銘柄", width="medium"),
                "短期スコア": st.column_config.NumberColumn("点数", format="%d", width="small"),
                "現在値": st.column_config.TextColumn("株価", width="small"),
                "決算": st.column_config.TextColumn("決算", width="small"),
                "急騰要因": st.column_config.TextColumn("要因", width="small")
            }
        else:
             cols_short = ["順位", "コード", "銘柄", "短期スコア", "現在値", "決算", "急騰要因"]
             cfg_short = {
                "順位": st.column_config.NumberColumn("Rank", width="small"),
                "短期スコア": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
                "決算": st.column_config.TextColumn("Earnings", width="small"),
                "急騰要因": st.column_config.TextColumn("Details", width="large")
            }

        event_short = st.dataframe(
            df_short[cols_short],
            column_config=cfg_short,
            height=600,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="df_short"
        )
        
        if len(event_short.selection.rows) > 0:
            row_idx = event_short.selection.rows[0]
            target_code = df_short.iloc[row_idx]['コード']
            st.session_state.ranking_target = target_code
            st.rerun()

# --- Helper Function for Analysis Rendering ---
def render_analysis_view(code_input):
    """Renders the analysis view for a given code."""
    try:
        metrics = get_strategy_metrics(code_input)
        name = get_stock_name(code_input)
        
        if metrics:
            # --- Fetch Analysis Data (Unified) ---
            advanced_stats = {}
            # 1. Try Cache
            try:
                scores = load_ranking_data()
                for row in scores:
                    if row['Code'] == str(code_input):
                        advanced_stats = row
                        break
            except: pass
            
            # 2. Try Fresh Analysis
            if not advanced_stats:
                try:
                    from analyze_nikkei_score import analyze_stock
                    advanced_stats = analyze_stock(code_input)
                except: pass
            
            param_score = advanced_stats.get('Score', '-') if advanced_stats else "-"
            
            # --- Header & Score ---
            st.subheader(f"{name} ({code_input})")
            
            # Score & Breakdown Column
            s1, s2 = st.columns([1, 2])
            with s1:
                st.metric("総合スコア", f"{param_score}点", help="トレンド・過熱感・リスクリワードから算出した、AIによる推奨度です。")
            

            
            # --- Metrics (Row 1) ---
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

            # Row 3: Advanced Stats
            if advanced_stats:
                st.markdown("---")
                # st.caption("**指標データ** (AI分析)") # Optional
                ac1, ac2, ac3, ac4 = st.columns(4)
                with ac1:
                    rsi_val = advanced_stats.get('RSI', 0)
                    st.metric("RSI(14)", f"{rsi_val:.1f}")
                with ac2:
                    pbr_val = advanced_stats.get('PBR', 0)
                    st.metric("PBR", f"{pbr_val:.2f}倍")
                with ac3:
                    per_val = advanced_stats.get('PER', 0)
                    st.metric("PER", f"{per_val:.1f}倍")
                with ac4:
                    score_rr = advanced_stats.get('RR', 0)
                    st.metric("R/R比", f"{score_rr:.2f}")


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
            
            # --- AI ANALYSIS REPORT ---
            st.markdown("---")
            st.subheader("📝 AI 総合分析レポート")
            
            analysis_text = ""
            if advanced_stats and 'AnalysisSummary' in advanced_stats:
                # Use the new comprehensive summary from analyze_stock
                analysis_text = advanced_stats['AnalysisSummary']
            else:
                # Fallback to the old simpler report from get_strategy_metrics
                analysis_text = metrics['DetailedReport']
            
            # Display inside a styled container for better readability
            st.markdown(f"""
            <div style="background-color: #2d3436; padding: 15px; border-radius: 10px; font-family: monospace; white-space: pre-wrap; line-height: 1.5;">
            {analysis_text}
            </div>
            """, unsafe_allow_html=True)
            
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
        
        c1, c2 = st.columns([1, 2])
        with c1:
            if st.button("🔄 ランキング更新"):
                st.cache_data.clear()
                st.rerun()

        try:
            with st.spinner("市場データを分析中... (1-2分かかります)"):
                scores = load_ranking_data()
            
            # Render the TABS inside this view
            render_ranking_view(scores)
                
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
