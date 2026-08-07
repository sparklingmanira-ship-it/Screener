import streamlit as st
import pandas as pd
import pandas_ta as ta
from tvDatafeed import TvDatafeed, Interval
import time
import numpy as np
import os

# =============================================================================
# 0. COMPATIBILITY PATCHES (DO NOT REMOVE)
# =============================================================================
# Fix for NumPy 2.0+
if not hasattr(np, 'NaN'):
    np.NaN = np.nan

# Fix for Pandas 2.0+ (Restores the .append method for pandas_ta)
if not hasattr(pd.Series, 'append'):
    pd.Series.append = lambda self, other, ignore_index=False, verify_integrity=False: pd.concat([self, other], ignore_index=ignore_index, verify_integrity=verify_integrity)
if not hasattr(pd.DataFrame, 'append'):
    pd.DataFrame.append = lambda self, other, ignore_index=False, verify_integrity=False: pd.concat([self, other], ignore_index=ignore_index, verify_integrity=verify_integrity)

# =============================================================================
# 1. PAGE CONFIGURATION & CACHING
# =============================================================================
st.set_page_config(
    page_title="Pro Stock Scanner v2.0",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

@st.cache_resource
def get_tv_connection():
    try:
        return TvDatafeed()
    except Exception as e:
        st.error(f"Failed to initialize TvDatafeed connection: {e}")
        return None

tv = get_tv_connection()

@st.cache_data(ttl=3600)
def get_benchmark_data():
    if tv:
        df = tv.get_hist(symbol='NIFTY', exchange='NSE', interval=Interval.in_daily, n_bars=400)
        if df is not None and not df.empty:
            return df['close']
    return None

benchmark_close = get_benchmark_data()

# =============================================================================
# 2. MARKET REGIME & SENTIMENT ENGINE
# =============================================================================
def analyze_market_regime(df, high_window=250):
    if df is None or len(df) < high_window:
        return "Unknown", "Insufficient Data", "N/A"
        
    df['ema_20'] = ta.ema(df['close'], 20)
    df['ema_50'] = ta.ema(df['close'], 50)
    df['ema_200'] = ta.ema(df['close'], 200)
    df['rsi_14'] = ta.rsi(df['close'], 14)
    df['52w_high'] = df['high'].rolling(window=high_window).max()
    
    latest = df.iloc[-1]
    
    close, ema20, ema50, ema200, rsi, high_52 = latest['close'], latest['ema_20'], latest['ema_50'], latest['ema_200'], latest['rsi_14'], latest['52w_high']
    dist_to_high = ((high_52 - close) / close) * 100
    
    if close < ema200 and rsi < 35:
        return "Crashing / Panicking", "Extreme Panic 🩸", "Volume Capitulation"
    elif dist_to_high <= 3.0 and close > ema20 and close > ema50:
        return "Making New Highs", "Greed / FOMO 🚀", "Macro Darvas, Unified EMA Pullback"
    elif close > ema50 and close > ema200:
        return "Slowly Grinding Up", "Optimism 📈", "Hidden Swing (VCP), Unified EMA Pullback"
    elif close < ema50 and close < ema200 and rsi >= 35:
        return "Slowly Grinding Down", "Fear 📉", "Relative Strength (Build Watchlists)"
    else:
        return "Sideways / Choppy", "Uncertainty ⚖️", "Anchored VWAP, Relative Strength"

# =============================================================================
# 3. STOCK SCANNING ENGINE (WITH DYNAMIC PARAMS)
# =============================================================================
def calc_macro_darvas(ticker, df, box_len, prox_pct):
    if len(df) < box_len + 10: return None 
    df['52w_high'] = df['high'].rolling(window=box_len).max()
    df['sma_200'] = ta.sma(df['close'], 200) 
    latest = df.iloc[-1]
    if latest['close'] > latest['sma_200']:
        dist_to_high = ((latest['52w_high'] - latest['close']) / latest['close']) * 100
        if 0 <= dist_to_high <= prox_pct:
            return {"Signal": "🟡 APPROACHING BREAKOUT", "Close": latest['close'], "Resistance": latest['52w_high']}
    return None

def calc_hidden_swing_vcp(ticker, df, comp_pct, vcp_days):
    if len(df) < 210: return None
    df['ema_50'] = ta.ema(df['close'], 50)
    df['ema_200'] = ta.ema(df['close'], 200)
    last_n_days = df.tail(vcp_days)
    compression_pct = ((last_n_days['high'].max() - last_n_days['low'].min()) / last_n_days['low'].min()) * 100
    latest = df.iloc[-1]
    if latest['close'] > latest['ema_50'] > latest['ema_200'] and compression_pct < comp_pct:
        return {"Signal": "🟢 VCP TIGHT", "Close": latest['close'], "Compression %": round(compression_pct, 2)}
    return None

def calc_unified_ema_pullback(ticker, df, target_ema, prox_pct):
    if len(df) < 210: return None
    df['ema_10'] = ta.ema(df['close'], 10)
    df['ema_20'] = ta.ema(df['close'], 20)
    df['ema_50'] = ta.ema(df['close'], 50)
    df['ema_200'] = ta.ema(df['close'], 200)
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], 14)
    latest = df.iloc[-1]
    
    if not (latest['ema_10'] > latest['ema_20'] > latest['ema_50'] > latest['ema_200']):
        return None
        
    ema_val = df[f'ema_{target_ema}'].iloc[-1]
    proximity = abs(latest['close'] - ema_val) / ema_val * 100
    if proximity <= prox_pct:
        stop_loss = latest['close'] - (latest['atr'] * 1.5)
        return {"Signal": f"🔵 {target_ema} EMA BOUNCE", "Close": latest['close'], "Stop Loss": round(stop_loss, 2)}
    return None

def calc_anchored_vwap(ticker, df, prox_pct):
    if len(df) < 260: return None
    high_idx = df.tail(250)['high'].idxmax()
    df_avwap = df.loc[high_idx:].copy()
    if len(df_avwap) < 5: return None 
    
    df_avwap['typical_price'] = (df_avwap['high'] + df_avwap['low'] + df_avwap['close']) / 3
    df_avwap['vol_price'] = df_avwap['typical_price'] * df_avwap['volume']
    df_avwap['cum_vol'] = df_avwap['volume'].cumsum()
    df_avwap['avwap'] = df_avwap['vol_price'].cumsum() / df_avwap['cum_vol']
    
    latest = df_avwap.iloc[-1]
    proximity = abs(latest['close'] - latest['avwap']) / latest['avwap'] * 100
    if proximity <= prox_pct and latest['close'] > latest['avwap']:
        return {"Signal": "🟣 AVWAP SUPPORT", "Close": latest['close'], "AVWAP Level": round(latest['avwap'], 2)}
    return None

def calc_relative_strength(ticker, df):
    if benchmark_close is None or len(df) < 260: return None
    combined = pd.DataFrame({'stock': df['close'], 'nifty': benchmark_close}).dropna()
    if len(combined) < 250: return None
    
    combined['rs_line'] = combined['stock'] / combined['nifty']
    latest_rs = combined['rs_line'].iloc[-1]
    rs_52w_high = combined['rs_line'].tail(250).max()
    latest_stock = combined['stock'].iloc[-1]
    stock_52w_high = combined['stock'].tail(250).max()
    
    if latest_rs >= rs_52w_high * 0.99 and latest_stock < stock_52w_high * 0.95:
         return {"Signal": "🔥 RS OUTPERFORMANCE", "Close": latest_stock}
    return None

def calc_volume_capitulation(ticker, df, rsi_thresh, vol_spike):
    if len(df) < 50: return None
    df['rsi'] = ta.rsi(df['close'], 14)
    df['ema_20'] = ta.ema(df['close'], 20)
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], 14)
    df['vol_sma20'] = ta.sma(df['volume'], 20)
    latest = df.iloc[-1]
    
    if latest['rsi'] < rsi_thresh and latest['close'] < (latest['ema_20'] - (2.5 * latest['atr'])):
        if latest['volume'] > (latest['vol_sma20'] * vol_spike):
            return {"Signal": "🩸 CAPITULATION BUY", "Close": latest['close'], "RSI": round(latest['rsi'], 2)}
    return None

# =============================================================================
# 4. SIDEBAR CONTROLS (RESTORED UPLOAD & PARAMS)
# =============================================================================

st.sidebar.title("🛠️ Scanner Controls")

# --- A. WATCHLIST MANAGEMENT ---
st.sidebar.header("📁 1. Watchlist")
default_watchlist = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "ITC", "SBIN", 
    "BHARTIARTL", "BAJFINANCE", "LT", "MM", "TATAMOTORS", "SUNPHARMA"
]
active_watchlist = default_watchlist.copy()

uploaded_file = st.sidebar.file_uploader("Upload CSV (Must have 'Symbol' column)", type=['csv'])

if uploaded_file is not None:
    try:
        custom_df = pd.read_csv(uploaded_file)
        if 'Symbol' in custom_df.columns:
            custom_symbols = custom_df['Symbol'].dropna().astype(str).tolist()
            # Clean symbols (remove .NS, .BO, and whitespace)
            custom_symbols = [s.replace('.NS', '').replace('.BO', '').strip() for s in custom_symbols]
            
            # Merge and remove duplicates
            active_watchlist = list(set(default_watchlist + custom_symbols))
            st.sidebar.success(f"Merged {len(custom_symbols)} custom stocks!")
        else:
            st.sidebar.error("CSV must contain a 'Symbol' column.")
    except Exception as e:
        st.sidebar.error(f"Error parsing CSV: {e}")

st.sidebar.markdown(f"**Total Stocks to Scan:** `{len(active_watchlist)}`")
st.sidebar.markdown("---")

# --- B. STRATEGY SELECTION ---
st.sidebar.header("🎯 2. Strategy")
selected_strategy = st.sidebar.selectbox(
    "Choose Active Scanner:",
    [
        "Macro Darvas Box Breakout",
        "Hidden Swing (VCP) Strategy",
        "Unified EMA Pullback",
        "Anchored VWAP (AVWAP)",
        "Relative Strength (vs NIFTY)",
        "Volume Capitulation (Mean Reversion)"
    ]
)

# --- C. DYNAMIC PARAMETERS ---
st.sidebar.header("⚙️ 3. Parameters")
params = {}

if selected_strategy == "Macro Darvas Box Breakout":
    params['box_len'] = st.sidebar.number_input("Box Lookback (Days)", min_value=50, max_value=500, value=250)
    params['prox_pct'] = st.sidebar.slider("Proximity to High (%)", 1.0, 10.0, 5.0, step=0.5)

elif selected_strategy == "Hidden Swing (VCP) Strategy":
    params['vcp_days'] = st.sidebar.slider("Compression Window (Days)", 3, 14, 7)
    params['comp_pct'] = st.sidebar.slider("Max Compression (%)", 1.0, 10.0, 4.0, step=0.5)

elif selected_strategy == "Unified EMA Pullback":
    params['target_ema'] = st.sidebar.selectbox("Moving Average Target", [10, 20, 50], index=1)
    params['prox_pct'] = st.sidebar.slider("Proximity to EMA (%)", 0.5, 5.0, 2.0, step=0.5)

elif selected_strategy == "Anchored VWAP (AVWAP)":
    params['prox_pct'] = st.sidebar.slider("Proximity to AVWAP (%)", 0.5, 5.0, 2.0, step=0.5)

elif selected_strategy == "Volume Capitulation (Mean Reversion)":
    params['rsi_thresh'] = st.sidebar.slider("Max RSI Threshold", 10, 40, 25)
    params['vol_spike'] = st.sidebar.slider("Volume Spike Multiplier", 1.5, 5.0, 3.0, step=0.5)

st.sidebar.markdown("---")
st.sidebar.header("⏱️ 4. Execution Settings")
delay = st.sidebar.slider("API Delay (seconds)", 0.5, 3.0, 1.0)


# =============================================================================
# 5. MAIN UI LAYOUT (TABS)
# =============================================================================
tab_scanner, tab_playbook = st.tabs(["📊 Scanner Engine", "📖 Strategy Playbook"])

# ----------------- SCANNER TAB -----------------
with tab_scanner:
    st.title("🚀 Professional Multi-Strategy Quant Scanner")
    st.markdown("*Institutional-grade structural setups, breakouts, and mean-reversion scanning.*")
    
    st.markdown("---")
    st.subheader("🌡️ NIFTY 50 Market Sentiment & Regime")
    
    col1, col2 = st.columns(2)
    if tv:
        nifty_daily = tv.get_hist(symbol='NIFTY', exchange='NSE', interval=Interval.in_daily, n_bars=400)
        if nifty_daily is not None:
            regime_d, emotion_d, rec_strat_d = analyze_market_regime(nifty_daily, high_window=250)
            col1.info(f"**DAILY TIMEFRAME (Short/Mid-Term)**\n\n**Regime:** {regime_d}\n\n**Mood:** {emotion_d}\n\n**Recommended Strategy:** {rec_strat_d}")
        
        nifty_weekly = tv.get_hist(symbol='NIFTY', exchange='NSE', interval=Interval.in_weekly, n_bars=200)
        if nifty_weekly is not None:
            regime_w, emotion_w, rec_strat_w = analyze_market_regime(nifty_weekly, high_window=52)
            col2.warning(f"**WEEKLY TIMEFRAME (Macro/Long-Term)**\n\n**Regime:** {regime_w}\n\n**Mood:** {emotion_w}\n\n**Recommended Strategy:** {rec_strat_w}")
            
    st.markdown("---")
    
    if st.button("▶️ Run Scanner on Watchlist", type="primary"):
        st.subheader(f"Results for: {selected_strategy}")
        
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, ticker in enumerate(active_watchlist):
            status_text.text(f"Scanning {ticker}... ({i+1}/{len(active_watchlist)})")
            progress_bar.progress((i + 1) / len(active_watchlist))
            
            try:
                df = tv.get_hist(symbol=ticker, exchange='NSE', interval=Interval.in_daily, n_bars=400)
                if df is not None and not df.empty:
                    signal_data = None
                    
                    if selected_strategy == "Macro Darvas Box Breakout":
                        signal_data = calc_macro_darvas(ticker, df, params['box_len'], params['prox_pct'])
                    elif selected_strategy == "Hidden Swing (VCP) Strategy":
                        signal_data = calc_hidden_swing_vcp(ticker, df, params['comp_pct'], params['vcp_days'])
                    elif selected_strategy == "Unified EMA Pullback":
                        signal_data = calc_unified_ema_pullback(ticker, df, params['target_ema'], params['prox_pct'])
                    elif selected_strategy == "Anchored VWAP (AVWAP)":
                        signal_data = calc_anchored_vwap(ticker, df, params['prox_pct'])
                    elif selected_strategy == "Relative Strength (vs NIFTY)":
                        signal_data = calc_relative_strength(ticker, df)
                    elif selected_strategy == "Volume Capitulation (Mean Reversion)":
                        signal_data = calc_volume_capitulation(ticker, df, params['rsi_thresh'], params['vol_spike'])
                    
                    if signal_data:
                        signal_data["Ticker"] = ticker
                        results.append(signal_data)
                        
                time.sleep(delay) 
                
            except Exception as e:
                pass # Fail silently on invalid tickers to keep scan moving
                
        status_text.text("Scan Complete!")
        progress_bar.empty()
        
        if results:
            formatted_results = [{ 'Ticker': r.pop('Ticker'), **r } for r in results]
            results_df = pd.DataFrame(formatted_results)
            st.dataframe(results_df, use_container_width=True)
            st.success(f"Found {len(results)} setups matching your criteria!")
        else:
            st.info("No stocks matched the current strategy parameters in your watchlist.")

# ----------------- PLAYBOOK TAB -----------------
with tab_playbook:
    st.header("📖 Trading Playbook & Market Regimes")
    st.markdown("**Rule of Thumb:** No strategy works in every environment. Trust the sentiment analyzer on the main tab to gauge the Nifty 50 context before trading.")
    
    st.subheader("🧭 Market Regime Cheat Sheet")
    regime_data = {
        "Nifty 50 Trend": ["Making New Highs", "Slowly Grinding Up", "Sideways / Choppy", "Slowly Grinding Down", "Crashing / Panicking"],
        "Market Emotion": ["Greed / FOMO", "Optimism", "Uncertainty", "Fear", "Extreme Panic"],
        "Strategy to Deploy": ["Macro Darvas Breakout, Unified EMA Pullback", "Hidden Swing (VCP), Unified EMA Pullback", "Anchored VWAP, Relative Strength", "Relative Strength (Build watchlists only)", "Volume Capitulation"]
    }
    st.table(pd.DataFrame(regime_data))
    
    st.markdown("---")
    st.subheader("📈 Strategy Breakdowns")
    
    with st.expander("1. Macro Darvas Box Breakout"):
        st.write("**The Logic:** Scans for stocks near a 52-week high that are consolidating in a long-term box, supported by a macro uptrend (above the 200 SMA proxy).")
        st.write("**Market Regime:** Strong Bull Markets.")
        
    with st.expander("2. Hidden Swing (VCP) Strategy"):
        st.write("**The Logic:** Looks for Volatility Contraction Patterns (VCP)—a 7-day period where the price range compresses to less than 4%.")
        st.write("**Market Regime:** Early Bull Markets or Post-Corrections.")
        
    with st.expander("3. Unified EMA Pullback"):
        st.write("**The Logic:** Finds stocks in a verified Stage 2 Uptrend (10 > 20 > 50 > 200 EMA) pulling back to your selected moving average.")
        st.write("**Market Regime:** Established Trending Markets.")
        
    with st.expander("4. Anchored VWAP (AVWAP) Support"):
        st.write("**The Logic:** Calculates the volume-weighted average price anchored to the 52-week high.")
        st.write("**Market Regime:** Choppy or Transitional Markets.")
        
    with st.expander("5. Relative Strength (vs NIFTY)"):
        st.write("**The Logic:** Identifies stocks making new 52-week Relative Strength highs while their actual price is not at a high (silent outperformance).")
        st.write("**Market Regime:** Bear Markets or Sideways Corrections.")
        
    with st.expander("6. Volume Capitulation (Mean Reversion)"):
        st.write("**The Logic:** 'Buy the blood.' Extreme oversold RSI (< 25), trading below 20 EMA, with massive panic volume.")
        st.write("**Market Regime:** Market Panics and Crashes.")