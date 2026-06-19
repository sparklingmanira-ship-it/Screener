import streamlit as st
import pandas_ta as ta
import pandas as pd
from tvDatafeed import TvDatafeed, Interval
import concurrent.futures
import os
import math

# --- INITIALIZATION ---
@st.cache_resource
def get_tv_connection():
    return TvDatafeed()

tv = get_tv_connection()

WATCHLIST_FILE = "saved_watchlist.csv"

st.set_page_config(page_title="Pro Stock Scanner", layout="wide")
st.title("🚀 Professional Multi-Strategy Scanner")

# --- WATCHLIST MANAGEMENT LOGIC ---
def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            df = pd.read_csv(WATCHLIST_FILE)
            if 'Symbol' in df.columns:
                return df['Symbol'].dropna().tolist()
        except Exception:
            pass
    
    default_tickers = [
        "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "BHARTIARTL", "INFY", "ITC", 
        "LT", "SBIN", "KOTAKBANK", "BAJFINANCE", "AXISBANK", "MARUTI", "SUNPHARMA"
    ]
    save_watchlist(default_tickers)
    return default_tickers

def save_watchlist(tickers):
    unique_tickers = sorted(list(set([str(t).strip().upper() for t in tickers])))
    pd.DataFrame({"Symbol": unique_tickers}).to_csv(WATCHLIST_FILE, index=False)
    return unique_tickers

scan_list = load_watchlist()

# --- SIDEBAR ---
st.sidebar.header("1. Select Strategy")
selected_strategy = st.sidebar.selectbox(
    "Which strategy do you want to run?",
    [
        "Hidden Swing Strategy", 
        "Institutional EMA Pullback v3",
        "SMA 14/28 Crossover",
        "NN50 EMA + Volume Scanner"
    ]
)

st.sidebar.markdown("---")
st.sidebar.header("2. Strategy Parameters")

params = {}
if selected_strategy == "Hidden Swing Strategy":
    params['req_trend'] = st.sidebar.checkbox("Require Stage 2 Trend (> 200 & 50 EMA)", value=True)
    params['min_strength'] = st.sidebar.number_input("Min 1-Month Return (%)", value=5.0, step=1.0)
    params['max_cons'] = st.sidebar.number_input("Max Consolidation Range (%)", value=3.0, step=0.5)

elif selected_strategy == "Institutional EMA Pullback v3":
    params['atr_mult'] = st.sidebar.number_input("ATR SL Multiplier", value=1.5, step=0.1, min_value=1.0, max_value=3.0)
    params['adx_thresh'] = st.sidebar.number_input("Min ADX for Entry", value=20, step=1, min_value=15, max_value=35)

elif selected_strategy == "SMA 14/28 Crossover":
    params['fast_sma'] = st.sidebar.number_input("Fast SMA Length", value=14, step=1)
    params['slow_sma'] = st.sidebar.number_input("Slow SMA Length", value=28, step=1)

elif selected_strategy == "NN50 EMA + Volume Scanner":
    params['vol_mult'] = st.sidebar.number_input("Volume > Avg Multiplier", value=1.3, step=0.1)
    params['prox_20'] = st.sidebar.number_input("20 EMA Proximity %", value=1.5, step=0.1)
    params['prox_50'] = st.sidebar.number_input("50 EMA Proximity %", value=2.0, step=0.1)

st.sidebar.markdown("---")
st.sidebar.header("3. Watchlist Management")
st.sidebar.info(f"📁 **{len(scan_list)}** stocks currently saved.")

uploaded_file = st.sidebar.file_uploader("Add stocks via CSV (Must have 'Symbol' column)", type=['csv'])

if uploaded_file is not None:
    if st.sidebar.button("➕ Merge & Save Uploaded List"):
        try:
            custom_df = pd.read_csv(uploaded_file)
            if 'Symbol' in custom_df.columns:
                new_tickers = custom_df['Symbol'].dropna().tolist()
                combined_list = scan_list + new_tickers
                save_watchlist(combined_list)
                st.sidebar.success(f"Added new stocks! Duplicates removed.")
                st.rerun() 
            else:
                st.sidebar.error("CSV missing 'Symbol' column.")
        except Exception as e:
            st.sidebar.error(f"Error: {e}")

if st.sidebar.button("🗑️ Reset to Default Watchlist"):
    if os.path.exists(WATCHLIST_FILE):
        os.remove(WATCHLIST_FILE)
    st.rerun()

# --- STRATEGY LOGIC FUNCTIONS ---

def calc_hidden_swing(ticker, df, params):
    df['ema200'] = ta.ema(df['Close'], 200)
    df['ema50']  = ta.ema(df['Close'], 50)
    current_close = df['Close'].iloc[-1]
    
    trend = True
    if params['req_trend']:
        trend = (current_close > df['ema200'].iloc[-1]) and (current_close > df['ema50'].iloc[-1])
    
    month_return = ((current_close - df['Close'].iloc[-21]) / df['Close'].iloc[-21]) * 100
    strength = month_return >= params['min_strength']
    
    h_high = df['High'].rolling(7).max().iloc[-1]
    l_low = df['Low'].rolling(7).min().iloc[-1]
    cons_range = ((h_high - l_low) / l_low) * 100
    structure = cons_range <= params['max_cons']
    
    if trend and strength and structure:
        return {"Ticker": ticker, "Close": round(current_close, 2), "1M Return": f"{round(month_return, 1)}%", "7D Range": f"{round(cons_range, 1)}%", "Signal": "🟢 SETUP READY"}
    return None

def calc_inst_ema_pullback_v3(ticker, df, params):
    # Macro Trend EMAs
    df['ema10']  = ta.ema(df['Close'], 10)
    df['ema21']  = ta.ema(df['Close'], 21)
    df['ema50']  = ta.ema(df['Close'], 50)
    df['ema200'] = ta.ema(df['Close'], 200)

    # Momentum & Volatility Indicators
    df['atr14'] = ta.atr(df['High'], df['Low'], df['Close'], 14)
    df['rsi14'] = ta.rsi(df['Close'], 14)
    df['vol_sma10'] = ta.sma(df['Volume'], 10)
    df['atr_sma20'] = ta.sma(df['atr14'], 20)
    df['swing_low_5'] = df['Low'].rolling(window=5).min()
    
    # Calculate Swing High for Fibonacci Target (10 period high)
    df['swing_high_10'] = df['High'].rolling(window=10).max()

    # ADX Calculation
    adx_df = ta.adx(df['High'], df['Low'], df['Close'], 14)
    if adx_df is not None and not adx_df.empty:
        df['adx']      = adx_df.iloc[:, 0]
        df['di_plus']  = adx_df.iloc[:, 1]
        df['di_minus'] = adx_df.iloc[:, 2]
    else:
        return None

    # Current and Historical Rows needed for condition checks
    curr = df.iloc[-1]
    prev1 = df.iloc[-2]
    prev2 = df.iloc[-3]
    prev3 = df.iloc[-4]

    # 1. Macro Trend Filter (Triple EMA)
    in_uptrend = (curr['Close'] > curr['ema21']) and (curr['ema21'] > curr['ema50']) and (curr['ema50'] > curr['ema200'])

    # 2. Dynamic Pullback Zone & Recovery
    pullback_zone = curr['ema10'] + (curr['atr14'] * 0.5)
    pulled_back = (prev1['Low'] <= pullback_zone) or (prev2['Low'] <= pullback_zone) or (prev3['Low'] <= pullback_zone)
    bullish_recovery = (curr['Close'] > curr['Open']) and (curr['Close'] > curr['ema10'])

    # 3. Volume Filters
    low_vol_pullback = prev1['Volume'] < (curr['vol_sma10'] * 0.85)
    good_recovery_vol = curr['Volume'] >= (curr['vol_sma10'] * 1.20)

    # 4. Momentum Filters
    rsi_ok = 45 <= curr['rsi14'] <= 75
    trend_strong = (curr['adx'] >= params['adx_thresh']) and (curr['di_plus'] > curr['di_minus'])

    # 5. Consolidation Guard
    not_consolidating = curr['atr14'] >= (curr['atr_sma20'] * 0.70)

    # 6. Stop Loss (ATR-based dynamic & Risk limit)
    atr_sl = curr['swing_low_5'] - (curr['atr14'] * params['atr_mult'])
    floor_sl = curr['Close'] * 0.94
    sl = max(atr_sl, floor_sl)
    risk_pct = ((curr['Close'] - sl) / curr['Close']) * 100
    acceptable_risk = risk_pct <= 7.0

    # 7. Fibonacci 1.618 Extension Target Calculation
    swing_high = curr['swing_high_10']
    swing_low = curr['swing_low_5']
    fib_range = swing_high - swing_low
    # Standard 1.618 extension measured from the recent pullback low
    fib_target = swing_low + (fib_range * 1.618)

    # Execute full setup match
    if (in_uptrend and pulled_back and bullish_recovery and low_vol_pullback and 
        good_recovery_vol and rsi_ok and trend_strong and not_consolidating and acceptable_risk):
        
        return {
            "Ticker": ticker, 
            "Entry Price": round(curr['Close'], 2), 
            "Stop Loss": round(sl, 2), 
            "Fib Target (1.618)": round(fib_target, 2),
            "Risk %": f"{round(risk_pct, 2)}%", 
            "RSI / ADX": f"{round(curr['rsi14'], 1)} / {round(curr['adx'], 1)}",
            "Signal": "🟢 V3 SETUP BUY"
        }
    return None

def calc_sma_crossover(ticker, df, params):
    fast_len, slow_len = params['fast_sma'], params['slow_sma']
    df['sma_fast'] = ta.sma(df['Close'], fast_len)
    df['sma_slow'] = ta.sma(df['Close'], slow_len)
    
    fast_curr, fast_prev = df['sma_fast'].iloc[-1], df['sma_fast'].iloc[-2]
    slow_curr, slow_prev = df['sma_slow'].iloc[-1], df['sma_slow'].iloc[-2]
    
    long_cond = (fast_curr > slow_curr) and (fast_prev <= slow_prev)
    short_cond = (fast_curr < slow_curr) and (fast_prev >= slow_prev)
    
    if long_cond:
        return {"Ticker": ticker, "Close": round(df['Close'].iloc[-1], 2), "Strategy": f"SMA {fast_len}/{slow_len}", "Signal": "🟢 LONG Crossover"}
    elif short_cond:
        return {"Ticker": ticker, "Close": round(df['Close'].iloc[-1], 2), "Strategy": f"SMA {fast_len}/{slow_len}", "Signal": "🔴 SHORT Crossunder"}
    return None

def calc_nn50_ema(ticker, df, params):
    df['ema20'] = ta.ema(df['Close'], 20)
    df['ema50'] = ta.ema(df['Close'], 50)
    df['vol_sma20'] = ta.sma(df['Volume'], 20)
    df['rsi14'] = ta.rsi(df['Close'], 14)
    
    curr_close = df['Close'].iloc[-1]
    curr_vol = df['Volume'].iloc[-1]
    
    high_vol = curr_vol > (df['vol_sma20'].iloc[-1] * params['vol_mult'])
    
    dist20 = abs(curr_close - df['ema20'].iloc[-1]) / df['ema20'].iloc[-1] * 100
    near20 = (dist20 <= params['prox_20']) and (df['ema20'].iloc[-1] > df['ema20'].iloc[-2])
    
    dist50 = abs(curr_close - df['ema50'].iloc[-1]) / df['ema50'].iloc[-1] * 100
    near50 = (dist50 <= params['prox_50']) and (curr_close > df['ema50'].iloc[-1]) and (df['ema50'].iloc[-1] >= df['ema50'].iloc[-2])
    
    curr_rsi = df['rsi14'].iloc[-1]
    rsi_ok = 45 <= curr_rsi <= 60
    
    scan20_ema = high_vol and near20 and rsi_ok
    scan50_ema = high_vol and near50 and rsi_ok
    
    if scan20_ema:
        return {"Ticker": ticker, "Close": round(curr_close, 2), "RSI": round(curr_rsi, 1), "Dist to 20EMA": f"{round(dist20, 2)}%", "Signal": "🔵 20 EMA Setup"}
    elif scan50_ema:
        return {"Ticker": ticker, "Close": round(curr_close, 2), "RSI": round(curr_rsi, 1), "Dist to 50EMA": f"{round(dist50, 2)}%", "Signal": "🟣 50 EMA Setup"}
    
    return None

# --- CORE SCANNING ENGINE ---
def scan_stock(ticker, strategy_name, strategy_params):
    try:
        clean_ticker = str(ticker).strip().replace('.NS', '')
        # Pulled 250 bars to assure enough history for the EMA 200 requirement
        df = tv.get_hist(symbol=clean_ticker, exchange='NSE', interval=Interval.in_daily, n_bars=250)
        
        if df is None or df.empty or len(df) < 200:
            return None 
            
        df.rename(columns={'close': 'Close', 'high': 'High', 'low': 'Low', 'volume': 'Volume', 'open': 'Open'}, inplace=True)
        
        # Router
        if strategy_name == "Hidden Swing Strategy":
            return calc_hidden_swing(clean_ticker, df, strategy_params)
        elif strategy_name == "Institutional EMA Pullback v3":
            return calc_inst_ema_pullback_v3(clean_ticker, df, strategy_params)
        elif strategy_name == "SMA 14/28 Crossover":
            return calc_sma_crossover(clean_ticker, df, strategy_params)
        elif strategy_name == "NN50 EMA + Volume Scanner":
            return calc_nn50_ema(clean_ticker, df, strategy_params)
            
    except Exception:
        return None
    return None

# --- UI EXECUTION ---
st.markdown(f"### Running: {selected_strategy}")

if st.button("▶️ Scan Saved Watchlist", type="primary"):
    
    st.write(f"Scanning {len(scan_list)} stocks. This may take a moment...")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    live_table_placeholder = st.empty() 
    results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(scan_stock, t, selected_strategy, params): t for t in scan_list}
        
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            res = future.result()
            if res:
                results.append(res)
                live_table_placeholder.dataframe(pd.DataFrame(results), use_container_width=True)
            
            current_prog = (i + 1) / len(scan_list)
            progress_bar.progress(current_prog)
            status_text.text(f"Processed {i+1}/{len(scan_list)} tickers...")
            
    st.success("Scan Complete!")
    
    if not results:
        live_table_placeholder.info("No stocks met the criteria for the selected strategy today.")