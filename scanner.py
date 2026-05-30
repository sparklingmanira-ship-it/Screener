import streamlit as st
import pandas_ta as ta
import pandas as pd
from tvDatafeed import TvDatafeed, Interval
import concurrent.futures
import os

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
        "Institutional 10EMA Pullback",
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

elif selected_strategy == "Institutional 10EMA Pullback":
    params['ema_len'] = st.sidebar.number_input("EMA Length", value=10, step=1)
    params['max_risk'] = st.sidebar.number_input("Max Risk %", value=3.0, step=0.5)

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

def calc_10ema_pullback(ticker, df, params):
    ema_len = params['ema_len']
    df[f'ema{ema_len}'] = ta.ema(df['Close'], ema_len)
    df['vol_sma10'] = ta.sma(df['Volume'], 10)
    
    curr_close = df['Close'].iloc[-1]
    curr_open  = df['Open'].iloc[-1]
    curr_ema   = df[f'ema{ema_len}'].iloc[-1]
    
    in_uptrend = curr_close > curr_ema
    ema_1, ema_2, ema_3 = df[f'ema{ema_len}'].iloc[-2], df[f'ema{ema_len}'].iloc[-3], df[f'ema{ema_len}'].iloc[-4]
    
    pulled_back = (df['Low'].iloc[-2] <= ema_1 * 1.02) or (df['Low'].iloc[-3] <= ema_2 * 1.02) or (df['Low'].iloc[-4] <= ema_3 * 1.02)
    bullish_recovery = (curr_close > curr_open) and (curr_close > curr_ema)
    low_vol = df['Volume'].iloc[-1] < (df['vol_sma10'].iloc[-1] * 0.9)
    
    swing_low = df['Low'].rolling(window=5).min().iloc[-1]
    risk_pct = ((curr_close - swing_low) / curr_close) * 100
    
    if in_uptrend and pulled_back and bullish_recovery and low_vol and (risk_pct <= params['max_risk']):
        return {"Ticker": ticker, "Close": round(curr_close, 2), "Risk %": f"{round(risk_pct, 2)}%", "Stop Loss": round(swing_low, 2), "Signal": "🟢 10EMA BUY"}
    return None

def calc_sma_crossover(ticker, df, params):
    fast_len, slow_len = params['fast_sma'], params['slow_sma']
    df['sma_fast'] = ta.sma(df['Close'], fast_len)
    df['sma_slow'] = ta.sma(df['Close'], slow_len)
    
    # Current and previous values for crossover check
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
    
    # 1. Volume Condition
    high_vol = curr_vol > (df['vol_sma20'].iloc[-1] * params['vol_mult'])
    
    # 2. 20 EMA Condition
    dist20 = abs(curr_close - df['ema20'].iloc[-1]) / df['ema20'].iloc[-1] * 100
    near20 = (dist20 <= params['prox_20']) and (df['ema20'].iloc[-1] > df['ema20'].iloc[-2])
    
    # 3. 50 EMA Condition
    dist50 = abs(curr_close - df['ema50'].iloc[-1]) / df['ema50'].iloc[-1] * 100
    near50 = (dist50 <= params['prox_50']) and (curr_close > df['ema50'].iloc[-1]) and (df['ema50'].iloc[-1] >= df['ema50'].iloc[-2])
    
    # 4. RSI Filter
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
        df = tv.get_hist(symbol=clean_ticker, exchange='NSE', interval=Interval.in_daily, n_bars=250)
        
        if df is None or df.empty or len(df) < 200:
            return None 
            
        df.rename(columns={'close': 'Close', 'high': 'High', 'low': 'Low', 'volume': 'Volume', 'open': 'Open'}, inplace=True)
        
        # Router
        if strategy_name == "Hidden Swing Strategy":
            return calc_hidden_swing(clean_ticker, df, strategy_params)
        elif strategy_name == "Institutional 10EMA Pullback":
            return calc_10ema_pullback(clean_ticker, df, strategy_params)
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