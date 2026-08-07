import concurrent.futures
import os
import re
import time
import urllib.parse
from bs4 import BeautifulSoup
from email.utils import parsedate_to_datetime
import pandas as pd
import pandas_ta as ta
import requests
import streamlit as st
from tvDatafeed import Interval, TvDatafeed

# =============================================================================
# 1. PAGE CONFIGURATION (MUST BE THE FIRST STREAMLIT COMMAND)
# =============================================================================
st.set_page_config(
    page_title="Pro Stock Scanner",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🚀 Professional Multi-Strategy Scanner")

# =============================================================================
# 2. INITIALIZATION & CACHING
# =============================================================================
WATCHLIST_FILE = "saved_watchlist.csv"

# Canonical Company Name Mapping for Query Precision & Disambiguation
COMPANY_NAME_MAP = {
    "RELIANCE": "Reliance Industries",
    "TCS": "Tata Consultancy Services",
    "HDFCBANK": "HDFC Bank",
    "ICICIBANK": "ICICI Bank",
    "BHARTIARTL": "Bharti Airtel",
    "INFY": "Infosys",
    "ITC": "ITC",
    "LT": "Larsen & Toubro",
    "ONGC": "ONGC",
    "SBIN": "State Bank of India",
    "KOTAKBANK": "Kotak Mahindra Bank",
    "BAJFINANCE": "Bajaj Finance",
    "AXISBANK": "Axis Bank",
    "MARUTI": "Maruti Suzuki",
    "SUNPHARMA": "Sun Pharma",
}


@st.cache_resource
def get_tv_connection():
    """Cache TvDatafeed connection to prevent redundant initializations across reruns."""
    try:
        return TvDatafeed()
    except Exception as e:
        st.error(f"Failed to initialize TvDatafeed connection: {e}")
        return None


tv = get_tv_connection()


# =============================================================================
# 3. WATCHLIST MANAGEMENT LOGIC
# =============================================================================
def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            df = pd.read_csv(WATCHLIST_FILE)
            if "Symbol" in df.columns:
                return df["Symbol"].dropna().tolist()
        except Exception:
            pass

    default_tickers = list(COMPANY_NAME_MAP.keys())
    save_watchlist(default_tickers)
    return default_tickers


def save_watchlist(tickers):
    unique_tickers = sorted(list(set([str(t).strip().upper() for t in tickers])))
    pd.DataFrame({"Symbol": unique_tickers}).to_csv(WATCHLIST_FILE, index=False)
    return unique_tickers


scan_list = load_watchlist()

# =============================================================================
# 4. SIDEBAR CONFIGURATION
# =============================================================================
st.sidebar.header("1. Select Strategy")
selected_strategy = st.sidebar.selectbox(
    "Which strategy do you want to run?",
    [
        "Institutional Brokerage News Radar",
        "Pro Institutional Swing Screener",
        "HACOLT & Range Filter Screener",
        "Hidden Swing Strategy",
        "Institutional EMA Pullback v3",
        "SMA 14/28 Crossover",
        "NN50 EMA + Volume Scanner",
        "Macro Darvas Box Breakout (Weekly Timeframe)",
        "Weekly Trend & Momentum",
    ],
)

st.sidebar.markdown("---")
st.sidebar.header("2. Strategy Parameters")

params = {}

if selected_strategy != "Institutional Brokerage News Radar":
    timeframe = st.sidebar.selectbox(
        "Select Timeframe",
        ["4 Hours", "1 Day", "1 Week", "1 Month"],
        index=1,
        help="Note: Darvas Box and Weekly Momentum permanently override this to 1 Week.",
    )
    params["timeframe"] = timeframe

if selected_strategy == "Institutional Brokerage News Radar":
    st.sidebar.markdown("**News Provider & Data Sources**")
    params["news_provider"] = st.sidebar.selectbox(
        "Select News Source",
        [
            "Google News RSS (Enhanced)",
            "Yahoo Finance RSS",
            "NSE Corporate Filings",
            "Combined (All Sources)",
        ],
        index=0,
        help="Choose between Google News, Yahoo Finance, or official NSE Exchange Disclosures.",
    )

    params["target_brokers"] = st.sidebar.multiselect(
        "Select Target Brokerages",
        [
            "Goldman Sachs",
            "Morgan Stanley",
            "JP Morgan",
            "JPMorgan",
            "Citi",
            "Macquarie",
            "Jefferies",
            "Nomura",
            "CLSA",
        ],
        default=["Goldman Sachs", "Morgan Stanley", "Citi", "Macquarie"],
    )

    st.sidebar.markdown("**Authentication & Reliability**")
    params["trusted_sources"] = st.sidebar.multiselect(
        "Permitted News Domains (Google News)",
        [
            "moneycontrol.com",
            "economictimes.indiatimes.com",
            "cnbctv18.com",
            "livemint.com",
            "bloomberg.com",
            "ndtvprofit.com",
        ],
        default=["moneycontrol.com", "economictimes.indiatimes.com", "cnbctv18.com"],
        help="Restricts Google News search to tier-1 financial publishers.",
    )

    params["req_keywords"] = st.sidebar.text_input(
        "Required Keywords (Comma separated)",
        "upgrade, downgrade, target, buy, sell, overweight, neutral, analyst, investor",
    )
    st.sidebar.info(
        "Scans real-time institutional calls & NSE exchange disclosures with enhanced company mapping."
    )

elif selected_strategy == "Pro Institutional Swing Screener":
    st.sidebar.markdown("**Liquidity & Volume**")
    params["min_avg_vol"] = st.sidebar.number_input(
        "Min 20-Day Avg Vol (Shares)", value=500000, step=50000
    )
    params["vol_surge_mult"] = st.sidebar.number_input(
        "Volume Surge Multiplier", value=1.5, step=0.1
    )

    st.sidebar.markdown("**Trend & Momentum**")
    params["req_ema_stack"] = st.sidebar.checkbox(
        "Require EMA Stack (Price > 20 > 50 EMA)", value=True
    )
    params["req_dow_trend"] = st.sidebar.checkbox(
        "Require Dow Theory (Higher Highs/Lows)", value=True
    )
    params["min_rsi"] = st.sidebar.number_input("Min RSI (14)", value=50.0, step=1.0)
    params["req_macd_bull"] = st.sidebar.checkbox("Require MACD > Signal", value=True)

    st.sidebar.markdown("**Risk Management**")
    params["min_rr"] = st.sidebar.number_input(
        "Min Reward-to-Risk Ratio", value=2.0, step=0.5
    )

elif selected_strategy == "HACOLT & Range Filter Screener":
    params["rf_period"] = st.sidebar.number_input("Range Filter Period", value=20, step=1)
    params["rf_mult"] = st.sidebar.number_input("Range Filter Multiplier", value=3.0, step=0.1)
    params["hacolt_period"] = st.sidebar.number_input("HACOLT Smooth Period", value=55, step=1)

elif selected_strategy == "Hidden Swing Strategy":
    params["req_trend"] = st.sidebar.checkbox("Require Stage 2 Trend (> 200 & 50 EMA)", value=True)
    params["min_strength"] = st.sidebar.number_input("Min 1-Month Return (%)", value=5.0, step=1.0)
    params["max_cons"] = st.sidebar.number_input("Max Consolidation Range (%)", value=3.0, step=0.5)

elif selected_strategy == "Institutional EMA Pullback v3":
    params["atr_mult"] = st.sidebar.number_input(
        "ATR SL Multiplier", value=1.5, step=0.1, min_value=1.0, max_value=3.0
    )
    params["adx_thresh"] = st.sidebar.number_input(
        "Min ADX for Entry", value=20, step=1, min_value=15, max_value=35
    )

elif selected_strategy == "SMA 14/28 Crossover":
    params["fast_sma"] = st.sidebar.number_input("Fast SMA Length", value=14, step=1)
    params["slow_sma"] = st.sidebar.number_input("Slow SMA Length", value=28, step=1)

elif selected_strategy == "NN50 EMA + Volume Scanner":
    params["vol_mult"] = st.sidebar.number_input("Volume > Avg Multiplier", value=1.3, step=0.1)
    params["prox_20"] = st.sidebar.number_input("20 EMA Proximity %", value=1.5, step=0.1)
    params["prox_50"] = st.sidebar.number_input("50 EMA Proximity %", value=2.0, step=0.1)

elif selected_strategy == "Macro Darvas Box Breakout (Weekly Timeframe)":
    params["box_len"] = st.sidebar.number_input("Macro Box Length (Weeks)", value=52, step=1)
    params["max_box_height"] = st.sidebar.number_input("Max Box Height (%)", value=60.0, step=5.0) / 100
    params["trend_sma_len"] = st.sidebar.number_input("Trend SMA Length (Weeks)", value=40, step=1)
    params["radar_pct"] = st.sidebar.number_input("Alert Proximity (%)", value=5.0, step=1.0) / 100
    params["use_trend_filter"] = st.sidebar.checkbox("Require 40-Week SMA Uptrend?", value=True)

    st.sidebar.markdown("**Smart Filters**")
    params["req_vol"] = st.sidebar.checkbox("Require Volume > 10W Avg", value=True)
    params["min_close_pct"] = (
        st.sidebar.number_input(
            "Min Close Near High (%)",
            value=50.0,
            step=5.0,
            help="50% means the candle closes in its upper half",
        )
        / 100
    )

elif selected_strategy == "Weekly Trend & Momentum":
    st.sidebar.markdown("**Lagging Trend Filters**")
    params["rsi_thresh"] = st.sidebar.number_input("Min RSI Level", value=40, step=1)
    params["adx_thresh"] = st.sidebar.number_input("Min ADX Level", value=20, step=1)

    st.sidebar.markdown("**Leading Smart Filters**")
    params["req_cmf"] = st.sidebar.checkbox(
        "Require CMF > 0 (Accumulation)", value=True, help="Institutions are buying"
    )
    params["req_stochrsi"] = st.sidebar.checkbox(
        "Require StochRSI Bullish", value=True, help="Momentum velocity is shifting up"
    )
    params["req_inside_bar"] = st.sidebar.checkbox(
        "Require Inside Bar (Contraction)", value=False, help="Volatility has dried up"
    )
    params["req_hidden_div"] = st.sidebar.checkbox(
        "Require Hidden Bull Div", value=False, help="Price forms higher low while RSI forms lower low"
    )

st.sidebar.markdown("---")
st.sidebar.header("3. Watchlist Management")
st.sidebar.info(f"📁 **{len(scan_list)}** stocks currently saved.")

uploaded_file = st.sidebar.file_uploader(
    "Add stocks via CSV (Must have 'Symbol' column)", type=["csv"]
)

if uploaded_file is not None:
    if st.sidebar.button("➕ Merge & Save Uploaded List"):
        try:
            custom_df = pd.read_csv(uploaded_file)
            if "Symbol" in custom_df.columns:
                new_tickers = custom_df["Symbol"].dropna().tolist()
                combined_list = scan_list + new_tickers
                save_watchlist(combined_list)
                st.sidebar.success("Added new stocks! Duplicates removed.")
                st.rerun()
            else:
                st.sidebar.error("CSV missing 'Symbol' column.")
        except Exception as e:
            st.sidebar.error(f"Error: {e}")

if st.sidebar.button("🗑️ Reset to Default Watchlist"):
    if os.path.exists(WATCHLIST_FILE):
        os.remove(WATCHLIST_FILE)
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.header("4. API Rate Limiter")
batch_size = st.sidebar.slider(
    "Batch Size (Concurrent Stocks)",
    min_value=1,
    max_value=20,
    value=5,
    help="Higher = Faster, but increases the risk of API rate-limiting.",
)
sleep_time = st.sidebar.slider(
    "Delay Between Batches (Seconds)",
    min_value=0.0,
    max_value=5.0,
    value=1.0,
    step=0.5,
)


# =============================================================================
# 5. ENHANCED NEWS PARSING & MULTI-SOURCE INTEGRATION (INCL. NSE FILINGS)
# =============================================================================
def extract_headline_details(text, brokers):
    """Parses text to extract brokerage name, call action, and target price."""
    text_lower = text.lower()

    matched_broker = "Broker Call / Disclosure"
    for b in brokers:
        if b.lower() in text_lower:
            matched_broker = b
            break

    buy_kw = [
        "upgrade", "upgraded", "buy", "overweight", "outperform",
        "top pick", "accumulate", "raises target", "raised target"
    ]
    sell_kw = [
        "downgrade", "downgraded", "sell", "underweight", "underperform",
        "cuts target", "cut target", "reduce"
    ]
    hold_kw = [
        "hold", "neutral", "equalweight", "equal-weight",
        "maintains buy", "retains", "maintain"
    ]

    if any(kw in text_lower for kw in buy_kw):
        action_call = "🟢 BUY / UPGRADE"
    elif any(kw in text_lower for kw in sell_kw):
        action_call = "🔴 SELL / DOWNGRADE"
    elif any(kw in text_lower for kw in hold_kw):
        action_call = "🟡 HOLD / NEUTRAL"
    else:
        action_call = "⚪ DISCLOSURE / REVIEW"

    target_pattern = r'(?:target|tp)(?:\s+price)?(?:\s+of|\s+at|\s+to|\s+set at|\s+raised to|\s+cut to)?\s*(?:rs\.?|₹)?\s*([\d,]+(?:\.\d+)?)'
    match = re.search(target_pattern, text_lower)

    target_price = "N/A"
    if match:
        target_price = f"₹{match.group(1).replace(',', '')}"
    else:
        alt_match = re.search(r'(?:rs\.?|₹)\s*([\d,]+(?:\.\d+)?)', text_lower)
        if alt_match:
            target_price = f"₹{alt_match.group(1).replace(',', '')}"

    return matched_broker, action_call, target_price


def fetch_google_news_rss(ticker, brokers, req_keywords, trusted_sources):
    """Fetches news from Google News RSS using precise intitle query & company mapping."""
    company_name = COMPANY_NAME_MAP.get(ticker, ticker)
    
    title_query = f'intitle:("{ticker}" OR "{company_name}")'
    broker_str = "(" + " OR ".join([f'"{b}"' for b in brokers]) + ")"
    
    if trusted_sources:
        site_str = "(" + " OR ".join([f"site:{site}" for site in trusted_sources]) + ")"
        query = f'{title_query} {broker_str} {site_str}'
    else:
        query = f'{title_query} {broker_str}'

    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"

    items_list = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        res = requests.get(url, headers=headers, timeout=6)
        if res.status_code == 200:
            soup = BeautifulSoup(res.content, "html.parser")
            items = soup.find_all("item")
            for item in items[:5]:
                raw_title = item.title.text if item.title else ""
                
                if " - " in raw_title:
                    title = raw_title.rsplit(" - ", 1)[0].strip()
                    publisher = raw_title.rsplit(" - ", 1)[-1].strip()
                else:
                    title = raw_title
                    source_tag = item.find("source")
                    publisher = source_tag.text if (source_tag and source_tag.text) else "Google News"

                pub_date_tag = item.find("pubDate") or item.find("pubdate")
                pub_date_raw = pub_date_tag.text if pub_date_tag else "N/A"

                items_list.append({
                    "title": title,
                    "description": "",
                    "full_text": title,
                    "publisher": publisher,
                    "pub_date_raw": pub_date_raw,
                    "source": "Google News"
                })
    except Exception:
        pass

    return items_list


def fetch_yahoo_finance_rss(ticker, brokers):
    """Fetches news directly from Yahoo Finance ticker-bound RSS feed."""
    yahoo_symbol = f"{ticker}.NS"
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={yahoo_symbol}&region=IN&lang=en-IN"
    
    items_list = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        res = requests.get(url, headers=headers, timeout=6)
        if res.status_code == 200:
            soup = BeautifulSoup(res.content, "html.parser")
            items = soup.find_all("item")
            for item in items[:5]:
                title = item.title.text if item.title else ""
                description = item.description.text if item.description else ""
                full_text = f"{title} {description}"
                
                pub_date_tag = item.find("pubDate") or item.find("pubdate")
                pub_date_raw = pub_date_tag.text if pub_date_tag else "N/A"

                items_list.append({
                    "title": title,
                    "description": description,
                    "full_text": full_text,
                    "publisher": "Yahoo Finance",
                    "pub_date_raw": pub_date_raw,
                    "source": "Yahoo Finance"
                })
    except Exception:
        pass

    return items_list


def fetch_nse_corporate_announcements(ticker):
    """Fetches official corporate disclosures & filings from the NSE India API."""
    clean_symbol = ticker.strip().upper()
    url = f"https://www.nseindia.com/api/corporate-announcements?index=equities&symbol={clean_symbol}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": f"https://www.nseindia.com/get-quotes/equity?symbol={clean_symbol}",
    }
    
    session = requests.Session()
    session.headers.update(headers)
    
    items_list = []
    try:
        # Establish session cookies
        session.get("https://www.nseindia.com", timeout=5)
        res = session.get(url, timeout=5)
        
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list):
                for item in data[:5]:
                    subject = item.get("desc", "") or item.get("attchmntText", "") or item.get("sm_subject", "")
                    details = item.get("attchmntText", "") or item.get("an_dt", "")
                    broadcast_dt = item.get("an_dt", "N/A")
                    
                    full_text = f"{subject} {details}"
                    items_list.append({
                        "title": subject,
                        "description": details,
                        "full_text": full_text,
                        "publisher": "NSE India Exchange",
                        "pub_date_raw": broadcast_dt,
                        "source": "NSE Filings"
                    })
    except Exception:
        pass
    
    return items_list


def calc_brokerage_news_radar(ticker, df, params):
    curr_close = (
        df["Close"].iloc[-1] if df is not None and not df.empty else "N/A"
    )

    brokers = params.get("target_brokers", [])
    raw_keywords = params.get("req_keywords", "")
    trusted_sources = params.get("trusted_sources", [])
    provider = params.get("news_provider", "Google News RSS (Enhanced)")

    req_keywords = [k.strip().lower() for k in raw_keywords.split(",") if k.strip()]

    raw_items = []
    if provider in ["Google News RSS (Enhanced)", "Combined (All Sources)"]:
        raw_items.extend(fetch_google_news_rss(ticker, brokers, req_keywords, trusted_sources))
    
    if provider in ["Yahoo Finance RSS", "Combined (All Sources)"]:
        raw_items.extend(fetch_yahoo_finance_rss(ticker, brokers))

    if provider in ["NSE Corporate Filings", "Combined (All Sources)"]:
        raw_items.extend(fetch_nse_corporate_announcements(ticker))

    company_name = COMPANY_NAME_MAP.get(ticker, ticker).lower()
    ticker_base = ticker.lower().split('-')[0]

    for item in raw_items:
        title = item.get("title", "")
        full_text = item.get("full_text", title)
        publisher = item.get("publisher", "News Source")
        pub_date_raw = item.get("pub_date_raw", "N/A")
        source = item.get("source", "RSS")

        text_to_check = full_text.lower()

        # Disambiguation Check
        ticker_match = (ticker_base in text_to_check) or (company_name in text_to_check) or (source == "NSE Filings")
        if not ticker_match:
            continue

        broker_match = any(b.lower() in text_to_check for b in brokers) if (brokers and source != "NSE Filings") else True
        if not broker_match:
            continue

        keyword_match = (
            any(k in text_to_check for k in req_keywords)
            if req_keywords
            else True
        )
        if not keyword_match:
            continue

        clean_date = "N/A"
        if pub_date_raw != "N/A":
            try:
                dt = parsedate_to_datetime(pub_date_raw)
                clean_date = dt.strftime("%d/%b/%y")
            except Exception:
                clean_date = str(pub_date_raw).replace(" GMT", "")

        matched_broker, action_call, target_price = extract_headline_details(full_text, brokers)

        return {
            "Ticker": ticker,
            "LTP": round(curr_close, 2) if isinstance(curr_close, float) else curr_close,
            "Brokerage": matched_broker if source != "NSE Filings" else "NSE Filing",
            "Call Signal": action_call,
            "Target Price": target_price,
            "Publisher": publisher,
            "Source": source,
            "Action Alert": title,
            "Published": clean_date,
        }

    return None


# =============================================================================
# 6. TECHNICAL STRATEGY CALCULATIONS
# =============================================================================
def calc_pro_institutional_swing(ticker, df, params):
    if len(df) < 60:
        return None

    curr_close = df["Close"].iloc[-1]
    curr_vol = df["Volume"].iloc[-1]

    df["vol_sma20"] = ta.sma(df["Volume"], 20)
    avg_vol_20 = df["vol_sma20"].iloc[-1]

    liquidity_ok = avg_vol_20 >= params["min_avg_vol"]
    vol_surge_ok = curr_vol >= (avg_vol_20 * params["vol_surge_mult"])

    if not (liquidity_ok and vol_surge_ok):
        return None

    df["ema20"] = ta.ema(df["Close"], 20)
    df["ema50"] = ta.ema(df["Close"], 50)

    ema_stacked = True
    if params["req_ema_stack"]:
        ema_stacked = (curr_close > df["ema20"].iloc[-1]) and (
            df["ema20"].iloc[-1] > df["ema50"].iloc[-1]
        )

    dow_trend = True
    if params["req_dow_trend"]:
        recent_high = df["High"].tail(10).max()
        prev_high = df["High"].iloc[-30:-10].max()
        recent_low = df["Low"].tail(10).min()
        prev_low = df["Low"].iloc[-30:-10].min()
        dow_trend = (recent_high > prev_high) and (recent_low > prev_low)

    if not (ema_stacked and dow_trend):
        return None

    df["rsi14"] = ta.rsi(df["Close"], 14)
    curr_rsi = df["rsi14"].iloc[-1]
    rsi_ok = curr_rsi >= params["min_rsi"]

    macd_ok = True
    if params["req_macd_bull"]:
        macd_df = ta.macd(df["Close"])
        if macd_df is not None and not macd_df.empty:
            macd_line = macd_df.iloc[:, 0].iloc[-1]
            macd_signal = macd_df.iloc.iloc[-1]
            macd_ok = macd_line > macd_signal
        else:
            macd_ok = False

    if not (rsi_ok and macd_ok):
        return None

    df["roc21"] = ta.roc(df["Close"], 21)
    curr_roc = df["roc21"].iloc[-1]
    rs_ok = curr_roc > 0

    if not rs_ok:
        return None

    support_level = df["Low"].tail(10).min()
    resistance_level = df["High"].tail(60).max()

    df["atr14"] = ta.atr(df["High"], df["Low"], df["Close"], 14)
    curr_atr = df["atr14"].iloc[-1]

    stop_loss = min(support_level, curr_close - (1.0 * curr_atr))
    risk = curr_close - stop_loss

    if risk <= 0:
        return None

    reward = resistance_level - curr_close

    if reward <= 0:
        return None

    rr_ratio = reward / risk

    if rr_ratio >= params["min_rr"]:
        vol_multiple = round(curr_vol / avg_vol_20, 2)
        return {
            "Ticker": ticker,
            "Entry": round(curr_close, 2),
            "Stop Loss": round(stop_loss, 2),
            "Target Resistance": round(resistance_level, 2),
            "R:R Ratio": f"{round(rr_ratio, 2)}:1",
            "Vol Surge": f"{vol_multiple}x",
            "RSI": round(curr_rsi, 1),
            "Signal": "🟢 PRO SWING SETUP",
        }

    return None


def calc_hacolt_rf(ticker, df, params):
    if len(df) < params["hacolt_period"] + 10:
        return None

    rf_period = params["rf_period"]
    rf_mult = params["rf_mult"]
    hacolt_period = params["hacolt_period"]

    df["smooth_price"] = ta.ema(df["Close"], length=5)
    df["tr"] = ta.true_range(df["High"], df["Low"], df["Close"])
    df["smooth_rng"] = ta.ema(df["tr"], length=rf_period) * rf_mult

    filt_val = [0.0] * len(df)
    rf_trend = [0] * len(df)

    for i in range(1, len(df)):
        prev_filt = filt_val[i - 1]
        smooth_price = df["smooth_price"].iloc[i]
        prev_smooth = df["smooth_price"].iloc[i - 1]
        smooth_rng = df["smooth_rng"].iloc[i]

        if pd.isna(smooth_price) or pd.isna(smooth_rng):
            filt_val[i] = prev_filt
            continue

        up_bound = smooth_price - smooth_rng
        dn_bound = smooth_price + smooth_rng

        if smooth_price > prev_filt:
            filt_val[i] = prev_filt if smooth_price < dn_bound else dn_bound
        else:
            filt_val[i] = prev_filt if smooth_price > up_bound else up_bound

        if smooth_price > filt_val[i] and prev_smooth <= prev_filt:
            rf_trend[i] = 1
        elif smooth_price < filt_val[i] and prev_smooth >= prev_filt:
            rf_trend[i] = -1
        else:
            rf_trend[i] = rf_trend[i - 1]

    df["rf_trend"] = rf_trend

    df["ha_close"] = (df["Open"] + df["High"] + df["Low"] + df["Close"]) / 4
    hacolt_ema1 = ta.ema(df["ha_close"], length=hacolt_period)
    hacolt_ema2 = ta.ema(hacolt_ema1, length=hacolt_period)
    df["hacolt_zl"] = hacolt_ema1 + (hacolt_ema1 - hacolt_ema2)

    df["hacolt_zl_highest_3"] = df["hacolt_zl"].rolling(3).max().shift(1)
    df["hacolt_zl_lowest_3"] = df["hacolt_zl"].rolling(3).min().shift(1)

    def get_hacolt_state(row):
        if row["hacolt_zl"] > row["hacolt_zl_highest_3"]:
            return 1
        elif row["hacolt_zl"] < row["hacolt_zl_lowest_3"]:
            return -1
        return 0

    df["hacolt_state"] = df.apply(get_hacolt_state, axis=1)

    df["system_state"] = 0
    df.loc[(df["rf_trend"] == 1) & (df["hacolt_state"] == 1), "system_state"] = 1
    df.loc[(df["rf_trend"] == -1) & (df["hacolt_state"] == -1), "system_state"] = -1

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    fresh_buy = curr["system_state"] == 1 and prev["system_state"] != 1
    fresh_sell = curr["system_state"] == -1 and prev["system_state"] != -1

    if fresh_buy:
        return {
            "Ticker": ticker,
            "Close": round(curr["Close"], 2),
            "Trend": "Bullish",
            "Signal": "🟢 FRESH BUY",
        }
    elif fresh_sell:
        return {
            "Ticker": ticker,
            "Close": round(curr["Close"], 2),
            "Trend": "Bearish",
            "Signal": "🔴 FRESH SELL",
        }

    return None


def calc_hidden_swing(ticker, df, params):
    df["ema200"] = ta.ema(df["Close"], 200)
    df["ema50"] = ta.ema(df["Close"], 50)
    current_close = df["Close"].iloc[-1]

    trend = True
    if params["req_trend"]:
        trend = (current_close > df["ema200"].iloc[-1]) and (
            current_close > df["ema50"].iloc[-1]
        )

    month_return = (
        (current_close - df["Close"].iloc[-21]) / df["Close"].iloc[-21]
    ) * 100
    strength = month_return >= params["min_strength"]

    h_high = df["High"].rolling(7).max().iloc[-1]
    l_low = df["Low"].rolling(7).min().iloc[-1]
    cons_range = ((h_high - l_low) / l_low) * 100
    structure = cons_range <= params["max_cons"]

    if trend and strength and structure:
        return {
            "Ticker": ticker,
            "Close": round(current_close, 2),
            "1M Return": f"{round(month_return, 1)}%",
            "7D Range": f"{round(cons_range, 1)}%",
            "Signal": "🟢 SETUP READY",
        }
    return None


def calc_inst_ema_pullback_v3(ticker, df, params):
    df["ema10"] = ta.ema(df["Close"], 10)
    df["ema21"] = ta.ema(df["Close"], 21)
    df["ema50"] = ta.ema(df["Close"], 50)
    df["ema200"] = ta.ema(df["Close"], 200)

    df["atr14"] = ta.atr(df["High"], df["Low"], df["Close"], 14)
    df["rsi14"] = ta.rsi(df["Close"], 14)
    df["vol_sma10"] = ta.sma(df["Volume"], 10)
    df["atr_sma20"] = ta.sma(df["atr14"], 20)
    df["swing_low_5"] = df["Low"].rolling(window=5).min()

    adx_df = ta.adx(df["High"], df["Low"], df["Close"], 14)
    if adx_df is not None and not adx_df.empty:
        df["adx"] = adx_df.iloc[:, 0]
        df["di_plus"] = adx_df.iloc
        df["di_minus"] = adx_df.iloc
    else:
        return None

    curr = df.iloc[-1]
    prev1 = df.iloc[-2]
    prev2 = df.iloc[-3]
    prev3 = df.iloc[-4]

    in_uptrend = (
        (curr["Close"] > curr["ema21"])
        and (curr["ema21"] > curr["ema50"])
        and (curr["ema50"] > curr["ema200"])
    )

    pullback_zone = curr["ema10"] + (curr["atr14"] * 0.5)
    pulled_back = (
        (prev1["Low"] <= pullback_zone)
        or (prev2["Low"] <= pullback_zone)
        or (prev3["Low"] <= pullback_zone)
    )
    bullish_recovery = (curr["Close"] > curr["Open"]) and (
        curr["Close"] > curr["ema10"]
    )

    low_vol_pullback = prev1["Volume"] < (curr["vol_sma10"] * 0.85)
    good_recovery_vol = curr["Volume"] >= (curr["vol_sma10"] * 1.20)

    rsi_ok = 45 <= curr["rsi14"] <= 75
    trend_strong = (curr["adx"] >= params["adx_thresh"]) and (
        curr["di_plus"] > curr["di_minus"]
    )

    not_consolidating = curr["atr14"] >= (curr["atr_sma20"] * 0.70)

    atr_sl = curr["swing_low_5"] - (curr["atr14"] * params["atr_mult"])
    floor_sl = curr["Close"] * 0.94
    sl = max(atr_sl, floor_sl)

    entry_price = curr["Close"]
    risk_points = entry_price - sl
    if risk_points <= 0:
        return None
    risk_pct = (risk_points / entry_price) * 100
    acceptable_risk = risk_pct <= 7.0

    t1 = entry_price + (risk_points * 1.0)
    t2 = entry_price + (risk_points * 2.0)
    t3 = entry_price + (risk_points * 3.0)

    if (
        in_uptrend
        and pulled_back
        and bullish_recovery
        and low_vol_pullback
        and good_recovery_vol
        and rsi_ok
        and trend_strong
        and not_consolidating
        and acceptable_risk
    ):
        return {
            "Ticker": ticker,
            "Entry": round(entry_price, 2),
            "Stop Loss": round(sl, 2),
            "T1 (1:1)": round(t1, 2),
            "T2 (1:2)": round(t2, 2),
            "T3 (1:3)": round(t3, 2),
            "Risk %": f"{round(risk_pct, 2)}%",
            "Signal": "🟢 V3 SETUP BUY",
        }
    return None


def calc_sma_crossover(ticker, df, params):
    fast_len, slow_len = params["fast_sma"], params["slow_sma"]
    df["sma_fast"] = ta.sma(df["Close"], fast_len)
    df["sma_slow"] = ta.sma(df["Close"], slow_len)

    fast_curr, fast_prev = df["sma_fast"].iloc[-1], df["sma_fast"].iloc[-2]
    slow_curr, slow_prev = df["sma_slow"].iloc[-1], df["sma_slow"].iloc[-2]

    long_cond = (fast_curr > slow_curr) and (fast_prev <= slow_prev)
    short_cond = (fast_curr < slow_curr) and (fast_prev >= slow_prev)

    if long_cond:
        return {
            "Ticker": ticker,
            "Close": round(df["Close"].iloc[-1], 2),
            "Strategy": f"SMA {fast_len}/{slow_len}",
            "Signal": "🟢 LONG Crossover",
        }
    elif short_cond:
        return {
            "Ticker": ticker,
            "Close": round(df["Close"].iloc[-1], 2),
            "Strategy": f"SMA {fast_len}/{slow_len}",
            "Signal": "🔴 SHORT Crossunder",
        }
    return None


def calc_nn50_ema(ticker, df, params):
    df["ema20"] = ta.ema(df["Close"], 20)
    df["ema50"] = ta.ema(df["Close"], 50)
    df["vol_sma20"] = ta.sma(df["Volume"], 20)
    df["rsi14"] = ta.rsi(df["Close"], 14)

    curr_close = df["Close"].iloc[-1]
    curr_vol = df["Volume"].iloc[-1]

    high_vol = curr_vol > (df["vol_sma20"].iloc[-1] * params["vol_mult"])

    dist20 = abs(curr_close - df["ema20"].iloc[-1]) / df["ema20"].iloc[-1] * 100
    near20 = (dist20 <= params["prox_20"]) and (
        df["ema20"].iloc[-1] > df["ema20"].iloc[-2]
    )

    dist50 = abs(curr_close - df["ema50"].iloc[-1]) / df["ema50"].iloc[-1] * 100
    near50 = (
        (dist50 <= params["prox_50"])
        and (curr_close > df["ema50"].iloc[-1])
        and (df["ema50"].iloc[-1] >= df["ema50"].iloc[-2])
    )

    curr_rsi = df["rsi14"].iloc[-1]
    rsi_ok = 45 <= curr_rsi <= 60

    scan20_ema = high_vol and near20 and rsi_ok
    scan50_ema = high_vol and near50 and rsi_ok

    if scan20_ema:
        return {
            "Ticker": ticker,
            "Close": round(curr_close, 2),
            "RSI": round(curr_rsi, 1),
            "Dist to 20EMA": f"{round(dist20, 2)}%",
            "Signal": "🔵 20 EMA Setup",
        }
    elif scan50_ema:
        return {
            "Ticker": ticker,
            "Close": round(curr_close, 2),
            "RSI": round(curr_rsi, 1),
            "Dist to 50EMA": f"{round(dist50, 2)}%",
            "Signal": "🟣 50 EMA Setup",
        }

    return None


def calc_macro_box_breakout_weekly(ticker, df, params):
    if len(df) < params["box_len"] + 2:
        return None

    box_len = params["box_len"]

    df["macro_sma"] = ta.sma(df["Close"], params["trend_sma_len"])
    df["vol_sma10"] = ta.sma(df["Volume"], 10)

    df["prev_high"] = df["High"].rolling(window=box_len).max().shift(1)
    df["curr_low"] = df["Low"].rolling(window=box_len).min().shift(1)

    curr = df.iloc[-1]

    prev_high = curr["prev_high"]
    curr_low = curr["curr_low"]
    curr_close = curr["Close"]

    is_uptrend = True
    if params["use_trend_filter"]:
        is_uptrend = curr_close > curr["macro_sma"]

    box_height_pct = (prev_high - curr_low) / curr_low
    valid_box = box_height_pct <= params["max_box_height"]

    has_volume = True
    if params["req_vol"]:
        has_volume = curr["Volume"] >= curr["vol_sma10"]

    candle_range = curr["High"] - curr["Low"]
    close_strength = True
    if candle_range > 0:
        close_pos = (curr_close - curr["Low"]) / candle_range
        close_strength = close_pos >= params["min_close_pct"]

    radar_zone_level = prev_high * (1 - params["radar_pct"])
    is_approaching = (curr_close >= radar_zone_level) and (
        curr_close < (prev_high * 0.99)
    )

    if is_approaching and valid_box and is_uptrend and has_volume and close_strength:
        dist_to_top = ((prev_high * 0.99) - curr_close) / curr_close * 100

        return {
            "Ticker": ticker,
            "LTP (Weekly)": round(curr_close, 2),
            "Box Resistance": round(prev_high, 2),
            "Gap to Breakout": f"{round(dist_to_top, 2)}%",
            "Close Strength": "Strong 💪",
            "Signal": "🟡 APPROACHING BREAKOUT",
        }
    return None


def calc_weekly_trend_momentum(ticker, df, params):
    if len(df) < 50:
        return None

    df["sma40"] = ta.sma(df["Close"], 40)
    df["rsi14"] = ta.rsi(df["Close"], 14)

    adx_df = ta.adx(df["High"], df["Low"], df["Close"], 14)
    if adx_df is not None and not adx_df.empty:
        df["adx"] = adx_df.iloc[:, 0]
    else:
        return None

    df["cmf"] = ta.cmf(
        df["High"], df["Low"], df["Close"], df["Volume"], length=20
    )

    stochrsi = ta.stochrsi(df["Close"], length=14, rsi_length=14, k=3, d=3)
    if stochrsi is not None and not stochrsi.empty:
        df["stoch_k"] = stochrsi.iloc[:, 0]
        df["stoch_d"] = stochrsi.iloc
    else:
        return None

    df["inside_bar"] = (df["High"] < df["High"].shift(1)) & (
        df["Low"] > df["Low"].shift(1)
    )

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    uptrend = curr["Close"] > curr["sma40"]
    rsi_ok = curr["rsi14"] >= params.get("rsi_thresh", 40)
    adx_ok = curr["adx"] >= params.get("adx_thresh", 20)

    cmf_ok = True
    if params["req_cmf"]:
        cmf_ok = curr["cmf"] > 0

    stoch_ok = True
    if params["req_stochrsi"]:
        stoch_ok = (curr["stoch_k"] > curr["stoch_d"]) and (curr["stoch_k"] < 80)

    inside_ok = True
    if params["req_inside_bar"]:
        inside_ok = curr["inside_bar"] or prev["inside_bar"]

    div_ok = True
    if params["req_hidden_div"]:
        recent_low = df["Low"].shift(1).rolling(10).min().iloc[-1]
        recent_rsi_low = df["rsi14"].shift(1).rolling(10).min().iloc[-1]
        div_ok = (curr["Low"] > recent_low) and (curr["rsi14"] < recent_rsi_low)

    if uptrend and rsi_ok and adx_ok and cmf_ok and stoch_ok and inside_ok and div_ok:
        return {
            "Ticker": ticker,
            "Close (Weekly)": round(curr["Close"], 2),
            "RSI": round(curr["rsi14"], 1),
            "CMF": round(curr["cmf"], 2),
            "Signal": "🔥 PRO SETUP",
        }
    return None


# =============================================================================
# 7. CORE SCANNING ENGINE
# =============================================================================
def scan_stock(ticker, strategy_name, strategy_params):
    try:
        clean_ticker = str(ticker).strip().replace(".NS", "")

        tf_mapping = {
            "4 Hours": Interval.in_4_hour,
            "1 Day": Interval.in_daily,
            "1 Week": Interval.in_weekly,
            "1 Month": Interval.in_monthly,
        }

        selected_interval = Interval.in_daily
        if "timeframe" in strategy_params:
            selected_interval = tf_mapping.get(
                strategy_params["timeframe"], Interval.in_daily
            )

        if strategy_name in [
            "Macro Darvas Box Breakout (Weekly Timeframe)",
            "Weekly Trend & Momentum",
        ]:
            selected_interval = Interval.in_weekly

        df = None
        if tv is not None:
            try:
                df = tv.get_hist(
                    symbol=clean_ticker,
                    exchange="NSE",
                    interval=selected_interval,
                    n_bars=400,
                )
            except Exception:
                df = None

        if (df is None or df.empty) and (
            strategy_name != "Institutional Brokerage News Radar"
        ):
            return None

        if df is not None and not df.empty:
            df.rename(
                columns={
                    "close": "Close",
                    "high": "High",
                    "low": "Low",
                    "volume": "Volume",
                    "open": "Open",
                },
                inplace=True,
            )

        if strategy_name == "Institutional Brokerage News Radar":
            return calc_brokerage_news_radar(clean_ticker, df, strategy_params)
        elif strategy_name == "Pro Institutional Swing Screener":
            return calc_pro_institutional_swing(clean_ticker, df, strategy_params)
        elif strategy_name == "HACOLT & Range Filter Screener":
            return calc_hacolt_rf(clean_ticker, df, strategy_params)
        elif strategy_name == "Hidden Swing Strategy":
            return calc_hidden_swing(clean_ticker, df, strategy_params)
        elif strategy_name == "Institutional EMA Pullback v3":
            return calc_inst_ema_pullback_v3(clean_ticker, df, strategy_params)
        elif strategy_name == "SMA 14/28 Crossover":
            return calc_sma_crossover(clean_ticker, df, strategy_params)
        elif strategy_name == "NN50 EMA + Volume Scanner":
            return calc_nn50_ema(clean_ticker, df, strategy_params)
        elif strategy_name == "Macro Darvas Box Breakout (Weekly Timeframe)":
            return calc_macro_box_breakout_weekly(clean_ticker, df, strategy_params)
        elif strategy_name == "Weekly Trend & Momentum":
            return calc_weekly_trend_momentum(clean_ticker, df, strategy_params)

    except Exception:
        return None
    return None


# =============================================================================
# 8. UI SCAN EXECUTION
# =============================================================================
st.markdown(f"### Running: {selected_strategy}")

if st.button("▶️ Scan Saved Watchlist", type="primary"):

    st.write(
        f"Scanning {len(scan_list)} stocks. (Batch Size: {batch_size}, Delay:"
        f" {sleep_time}s)..."
    )

    progress_bar = st.progress(0)
    status_text = st.empty()
    live_table_placeholder = st.empty()
    results = []

    for i in range(0, len(scan_list), batch_size):
        batch = scan_list[i : i + batch_size]

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=batch_size
        ) as executor:
            futures = {
                executor.submit(
                    scan_stock, t, selected_strategy, params
                ): t
                for t in batch
            }

            for future in concurrent.futures.as_completed(futures):
                res = future.result()
                if res:
                    results.append(res)

        # Batch update UI table
        if results:
            live_table_placeholder.dataframe(
                pd.DataFrame(results), use_container_width=True
            )

        processed_count = min(i + batch_size, len(scan_list))
        current_prog = processed_count / len(scan_list)
        progress_bar.progress(current_prog)
        status_text.text(f"Processed {processed_count}/{len(scan_list)} tickers...")

        if processed_count < len(scan_list) and sleep_time > 0:
            time.sleep(sleep_time)

    st.success("Scan Complete!")

    if results:
        results_df = pd.DataFrame(results)
        csv_data = results_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download Results CSV",
            data=csv_data,
            file_name=f"scan_results_{selected_strategy.replace(' ', '_').lower()}.csv",
            mime="text/csv",
        )
    else:
        live_table_placeholder.info(
            "No stocks met the criteria for the selected strategy today."
        )