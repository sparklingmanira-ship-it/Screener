# 🚀 Professional Multi-Strategy Stock Scanner

A high-performance, Python-based desktop stock screener built with Streamlit. It fetches live end-of-day data directly from TradingView and scans hundreds of NSE stocks in seconds using parallel processing.

## ✨ Features
* **Multi-Strategy Engine:** Instantly switch between multiple technical analysis strategies via the sidebar.
* **Direct TradingView Data:** Uses `tvDatafeed` to pull accurate OHLCV data directly from TradingView's servers without needing an API key.
* **Live Dynamic UI:** Results populate in real-time as the background scanner processes the watchlist.
* **Smart Watchlist Management:** Upload custom CSV watchlists. The app automatically deduplicates, sorts, and saves your master list locally so it remembers your stocks for next time.
* **Mobile Ready:** Access the dashboard seamlessly on your mobile phone via your local Wi-Fi network.

## 📈 Included Strategies

1. **Hidden Swing Strategy:** Looks for Stage 2 uptrends (Price > 50 & 200 EMA) with strong 1-month momentum (>5%) that are currently in a tight consolidation phase (adjustable range).
2. **Institutional 10EMA Pullback:** Scans for stocks in a strong uptrend that have pulled back to the 10 EMA on low volume, printing a bullish recovery candle. Calculates a 1:2 Risk/Reward target automatically.
3. **SMA 14/28 Crossover:** A classic momentum strategy that triggers signals exactly when the 14-day Simple Moving Average crosses above or below the 28-day Simple Moving Average.
4. **NN50 EMA + Volume Scanner:** Hunts for high-volume breakouts occurring within close proximity (tight percentage range) to the 20-day or 50-day EMA while RSI remains in a healthy 45-60 zone.

## 🛠️ Prerequisites
* **Python 3.9+** installed on your system.
* **Git** (Required to install the TradingView datafeed library).

## 📦 Installation

1. **Open your terminal or command prompt.**
2. **Install the core libraries:**
   ```bash
   pip install streamlit pandas pandas-ta
