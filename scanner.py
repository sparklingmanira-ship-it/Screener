import streamlit as st
import pandas as pd
import pandas_ta as ta
from tvDatafeed import TvDatafeed, Interval
import time

if not hasattr(np, 'NaN'):
    np.NaN = np.nan

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
    """Cache TvDatafeed connection to prevent redundant initializations."""
    try:
        return TvDatafeed()
    except Exception as e:
        st.error(f"Failed to initialize TvDatafeed connection: {e}")
        return None

tv = get_tv_connection()

@st.cache_data(ttl=3600)
def get_benchmark_data():
    """Fetches Nifty 50 data to calculate Relative Strength (RS)."""
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
    """
    Analyzes the index dataframe to determine the current market regime based on the playbook.
    """
    if df is None or len(df) < high_window:
        return "Unknown", "Insufficient Data", "N/A"
        
    df['ema_20'] = ta.ema(df['close'], 20)
    df['ema_50'] = ta.ema(df['close'], 50)
    df['ema_200'] = ta.ema(df['close'], 200)
    df['rsi_14'] = ta.rsi(df['close'], 14)
    df['52w_high'] = df['high'].rolling(window=high_window).max()
    
    latest = df.iloc[-1]
    
    close = latest['close']
    ema20 = latest['ema_20']
    ema50 = latest['ema_50']
    ema200 = latest['ema_200']
    rsi = latest['rsi_14']
    high_52 = latest['52w_high']
    
    dist_to_high = ((high_52 - close) / close) * 100
    
    # Regime Logic mapped to the Playbook
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
# 3. STOCK SCANNING ENGINE
# =============================================================================

def calc_macro_darvas(ticker, df):
    if len(df) < 260: return None 
    df['52w_high'] = df['high'].rolling(window=250).max()
    df['sma_200'] = ta.sma(df['close'], 200) 
    latest = df.iloc[-1]
    if latest['close'] > latest['sma_200']:
        dist_to_high = ((latest['52w_high'] - latest['close']) / latest['close']) * 100
        if 0 <= dist_to_high <= 5.0:
            return {"Signal": "🟡 APPROACHING BREAKOUT", "Close": latest['close'], "Resistance": latest['52w_high']}
    return None

def calc_hidden_swing_vcp(ticker, df):
    if len(df) < 210: return None
    df['ema_50'] = ta.ema(df['close'], 50)
    df['ema_200'] = ta.ema(df['close'], 200)
    last_7_days = df.tail(7)
    compression_pct = ((last_7_days['high'].max() - last_7_days['low'].min()) / last_7_days['low'].min()) * 100
    latest = df.iloc[-1]
    if latest['close'] > latest['ema_50'] > latest['ema_200'] and compression_pct < 4.0:
        return {"Signal": "🟢 VCP TIGHT", "Close": latest['close'], "Compression %": round(compression_pct, 2)}
    return None

def calc_unified_ema_pullback(ticker, df, target_ema=20):
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
    if proximity <= 2.0:
        stop_loss = latest['close'] - (latest['atr'] * 1.5)
        return {"Signal": f"🔵 {target_ema} EMA BOUNCE", "Close": latest['close'], "Stop Loss": round(stop_loss, 2)}
    return None

def calc_anchored_vwap(ticker, df):
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
    if proximity <= 2.0 and latest['close'] > latest['avwap']:
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

def calc_volume_capitulation(ticker, df):
    if len(df) < 50: return None
    df['rsi'] = ta.rsi(df['close'], 14)
    df['ema_20'] = ta.ema(df['close'], 20)
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], 14)
    df['vol_sma20'] = ta.sma(df['volume'], 20)
    latest = df.iloc[-1]
    
    if latest['rsi'] < 25 and latest['close'] < (latest['ema_20'] - (2.5 * latest['atr'])):
        if latest['volume'] > (latest['vol_sma20'] * 3):
            return {"Signal": "🩸 CAPITULATION BUY", "Close": latest['close'], "RSI": round(latest['rsi'], 2)}
    return None

# =============================================================================
# 4. SIDEBAR CONTROLS
# =============================================================================

st.sidebar.header("1. Strategy Selection")
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

target_ema_param = 20
if selected_strategy == "Unified EMA Pullback":
    st.sidebar.markdown("---")
    st.sidebar.header("2. Strategy Parameters")
    target_ema_param = st.sidebar.selectbox("Select Moving Average Target", [10, 20, 50], index=1)

st.sidebar.markdown("---")
st.sidebar.header("3. Execution Settings")
delay = st.sidebar.slider("API Delay (seconds)", 0.5, 3.0, 1.0, help="Prevents tvDatafeed rate limits.")

default_watchlist = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", 
    "ITC", "SBIN", "BHARTIARTL", "BAJFINANCE", "LT", "MM",
    "TATAMOTORS", "SUNPHARMA", "MARUTI", "KOTAKBANK", "ASIANPAINT"
]

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
    
    # Fetch Nifty data for sentiment analysis
    col1, col2 = st.columns(2)
    
    if tv:
        # Daily Sentiment
        nifty_daily = tv.get_hist(symbol='NIFTY', exchange='NSE', interval=Interval.in_daily, n_bars=400)
        if nifty_daily is not None:
            regime_d, emotion_d, rec_strat_d = analyze_market_regime(nifty_daily, high_window=250)
            col1.info(f"**DAILY TIMEFRAME (Short/Mid-Term)**\n\n**Regime:** {regime_d}\n\n**Mood:** {emotion_d}\n\n**Recommended Strategy:** {rec_strat_d}")
        
        # Weekly Sentiment
        nifty_weekly = tv.get_hist(symbol='NIFTY', exchange='NSE', interval=Interval.in_weekly, n_bars=200)
        if nifty_weekly is not None:
            regime_w, emotion_w, rec_strat_w = analyze_market_regime(nifty_weekly, high_window=52) # 52 weeks = 1 year
            col2.warning(f"**WEEKLY TIMEFRAME (Macro/Long-Term)**\n\n**Regime:** {regime_w}\n\n**Mood:** {emotion_w}\n\n**Recommended Strategy:** {rec_strat_w}")
            
    st.markdown("---")
    
    # Scanner Execution
    if st.button("▶️ Run Scanner", type="primary"):
        st.subheader(f"Results for: {selected_strategy}")
        
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, ticker in enumerate(default_watchlist):
            status_text.text(f"Scanning {ticker}... ({i+1}/{len(default_watchlist)})")
            progress_bar.progress((i + 1) / len(default_watchlist))
            
            try:
                df = tv.get_hist(symbol=ticker, exchange='NSE', interval=Interval.in_daily, n_bars=400)
                if df is not None and not df.empty:
                    signal_data = None
                    
                    if selected_strategy == "Macro Darvas Box Breakout":
                        signal_data = calc_macro_darvas(ticker, df)
                    elif selected_strategy == "Hidden Swing (VCP) Strategy":
                        signal_data = calc_hidden_swing_vcp(ticker, df)
                    elif selected_strategy == "Unified EMA Pullback":
                        signal_data = calc_unified_ema_pullback(ticker, df, target_ema_param)
                    elif selected_strategy == "Anchored VWAP (AVWAP)":
                        signal_data = calc_anchored_vwap(ticker, df)
                    elif selected_strategy == "Relative Strength (vs NIFTY)":
                        signal_data = calc_relative_strength(ticker, df)
                    elif selected_strategy == "Volume Capitulation (Mean Reversion)":
                        signal_data = calc_volume_capitulation(ticker, df)
                    
                    if signal_data:
                        signal_data["Ticker"] = ticker
                        results.append(signal_data)
                        
                time.sleep(delay) 
                
            except Exception as e:
                st.error(f"Error scanning {ticker}: {e}")
                
        status_text.text("Scan Complete!")
        
        if results:
            formatted_results = [{ 'Ticker': r.pop('Ticker'), **r } for r in results]
            results_df = pd.DataFrame(formatted_results)
            st.dataframe(results_df, use_container_width=True)
            st.success(f"Found {len(results)} setups matching your criteria!")
        else:
            st.info("No stocks currently match this strategy's criteria in the provided watchlist.")

# ----------------- PLAYBOOK TAB -----------------
with tab_playbook:
    st.header("📖 Trading Playbook & Market Regimes")
    st.markdown("""
    **Rule of Thumb:** No strategy works in every environment. Trust the sentiment analyzer on the main tab to gauge the Nifty 50 context before trading.
    """)
    
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
        st.write("**How to Trade:** Place buy stop orders just above the 52-week high. Do not anticipate the breakout; wait for the price to prove it. Stop loss goes below the middle of the box.")
        
    with st.expander("2. Hidden Swing (VCP) Strategy"):
        st.write("**The Logic:** Looks for Volatility Contraction Patterns (VCP)—a 7-day period where the price range compresses to less than 4%.")
        st.write("**Market Regime:** Early Bull Markets or Post-Corrections.")
        st.write("**How to Trade:** Buy as the stock breaks out of that tight 7-day range on higher-than-average volume. Place a tight stop loss (3-4% below entry).")
        
    with st.expander("3. Unified EMA Pullback"):
        st.write("**The Logic:** Finds stocks in a verified Stage 2 Uptrend (10 > 20 > 50 > 200 EMA) pulling back to your selected moving average.")
        st.write("**Market Regime:** Established Trending Markets.")
        st.write("**How to Trade:** Use the 10 EMA for hyper-aggressive momentum, 20 EMA for standard swing trades, and 50 EMA for large-cap support. Wait for a bullish hammer or engulfing candle off the line before entering.")
        
    with st.expander("4. Anchored VWAP (AVWAP) Support"):
        st.write("**The Logic:** Calculates the volume-weighted average price anchored to the 52-week high.")
        st.write("**Market Regime:** Choppy or Transitional Markets.")
        st.write("**How to Trade:** Buy the bounce off this line when a stock pulls back to it on decreasing volume. It indicates institutions are defending their break-even price.")
        
    with st.expander("5. Relative Strength (vs NIFTY)"):
        st.write("**The Logic:** Identifies stocks making new 52-week Relative Strength highs while their actual price is not at a high (silent outperformance).")
        st.write("**Market Regime:** Bear Markets or Sideways Corrections.")
        st.write("**How to Trade:** Add to a watchlist. Do not buy while the market is crashing. When the Nifty turns green, these will explode upward.")
        
    with st.expander("6. Volume Capitulation (Mean Reversion)"):
        st.write("**The Logic:** 'Buy the blood.' Extreme oversold RSI (< 25), trading below 20 EMA, with massive panic volume.")
        st.write("**Market Regime:** Market Panics and Crashes.")
        st.write("**How to Trade:** Buy near the close of the day on an exhaustion gap or long lower wick. Hold for 1 to 3 days maximum for a dead cat bounce.")