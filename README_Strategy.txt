# 🚀 Professional Multi-Strategy Scanner: User Guide

Welcome to the **Pro Stock Scanner**! This Streamlit application is designed to help you scan the Indian Stock Market (NSE) using advanced technical analysis and institutional-grade trading setups.

This README will guide you through how to use the scanner, manage your watchlists, and understand the logic behind each of the seven built-in trading strategies.

---

## ⚙️ How to Use the Scanner

1. **Select a Strategy:** Use the sidebar on the left to choose which trading strategy you want to scan for.
2. **Tune the Parameters:** Once a strategy is selected, dynamic parameters will appear below it. You can adjust these to be as strict or loose as the current market conditions require (e.g., toggling Smart Filters or adjusting RSI thresholds).
3. **Select Your Timeframe:** Certain strategies (like the HACOLT Range Filter) support dynamic multi-timeframe analysis (4 Hours, 1 Day, 1 Week, 1 Month). Select your preferred timeframe from the dropdown. 
4. **Manage Your Watchlist:** The scanner runs through a specific list of stocks.
* You can upload a custom CSV file (it must contain a column named exactly `Symbol`).
* You can click "Merge & Save Uploaded List" to combine your custom stocks with the default ones.
* Click "Reset to Default Watchlist" to revert to the base Nifty 50/Bank Nifty heavyweights.

5. **Run the Scan:** Click the primary **▶️ Scan Saved Watchlist** button. The app processes stocks sequentially (to prevent TradingView connection bans) and will output a clean data table of any stock that perfectly matches your criteria.

---

## 📈 Strategy Breakdown

Here is exactly what the engine is looking for under the hood for each strategy.

### 1. HACOLT & Range Filter Screener Engine (Multi-Timeframe)

**Best For:** Trend-followers utilizing 2-3 week swing trades or multi-timeframe alignment across 4H/1D/1W charts. 

* **The Logic:** Combines Sylvain Vervoort's Long Term HA Oscillator (HACOLT) zero-lag proxy with an adaptive price Range Filter. 
* **The Trigger:** Scans for the exact moment when *both* the smoothed price breaches the Range Filter bounds AND the HA Oscillator crosses its signal line, assigning a synchronized Bullish/Bearish State. 
* **Signal Output:** 🟢 `FRESH BUY` or 🔴 `FRESH SELL`

### 2. Macro Darvas Box Breakout (Weekly Timeframe)

**Best For:** Position traders looking for massive, multi-month breakouts out of long-term consolidations.

* **The Logic:** Looks for stocks consolidating in a 52-week (1-year) box that are within 5% of breaking out to new highs.
* **Core Filters:** Requires the stock to be in a long-term uptrend (above the 40-Week SMA) and the box height cannot exceed your maximum depth parameter (default 60%).
* **Smart Filters:**
* *Volume Check:* Ensures current weekly volume is higher than the 10-week average (institutions are participating).
* *Close Strength:* Ensures the weekly candle closes near its highs (buyers are holding through the weekend).

* **Signal Output:** 🟡 `APPROACHING BREAKOUT`

### 3. Weekly Trend & Momentum (Pro Setup)

**Best For:** Swing traders looking to catch explosive momentum shifts on a higher timeframe *before* they become obvious to retail traders.

* **Lagging (Core) Filters:** Ensures the stock is fundamentally bullish (Price > 40-Week SMA, RSI > 40, ADX > 20).
* **Leading (Smart) Filters (Toggleable):**
* *Chaikin Money Flow (CMF > 0):* Detects stealth institutional accumulation based on volume flow.
* *StochRSI Bullish:* Detects a sharp shift in momentum velocity before standard MACD crossovers occur.
* *Inside Bar:* Looks for volatility contraction—a quiet, tight week that often precedes a violent breakout.
* *Hidden Bullish Divergence:* Looks for price making a higher low while RSI makes a lower low (a hidden slingshot setup).

* **Signal Output:** 🔥 `PRO SETUP`

### 4. Institutional EMA Pullback v3 (Daily)

**Best For:** Trend-followers looking to "buy the dip" in heavily trending stocks.

* **The Logic:** Finds stocks in a verified Stage 2 Uptrend (10 > 21 > 50 > 200 EMA) that have recently pulled back into the "value zone" (near the 10 EMA).
* **Validation:** It checks for volume dry-up during the pullback (no heavy selling) and high volume on the bullish recovery candle. It also filters out choppy markets by requiring a strong ADX trend and expanding ATR.
* **Risk Management Built-In:** Automatically calculates an ATR-based stop loss and provides exact price targets for 1:1, 1:2, and 1:3 Risk/Reward ratios.
* **Signal Output:** 🟢 `V3 SETUP BUY`

### 5. Hidden Swing Strategy (Daily)

**Best For:** Quick momentum bursts out of tight, short-term flags.

* **The Logic:** Requires the stock to be in a macro uptrend and have shown strong momentum over the last month (e.g., > 5% return).
* **The Trigger:** It scans for a 7-day period of extreme price compression (tight consolidation), signaling that the stock is resting before its next leg up.
* **Signal Output:** 🟢 `SETUP READY`

### 6. NN50 EMA + Volume Scanner (Daily)

**Best For:** Finding active, high-volume bounces off key moving averages.

* **The Logic:** Scans for stocks that are trading very close (within 1.5% to 2%) of either their 20-day or 50-day EMA.
* **The Trigger:** Requires the current daily volume to be significantly higher than the 20-day average volume, combined with a neutral RSI (45 to 60) so you aren't buying overbought extensions.
* **Signal Output:** 🔵 `20 EMA Setup` or 🟣 `50 EMA Setup`

### 7. SMA 14/28 Crossover (Daily)

**Best For:** Beginners or algorithmic baseline testing.

* **The Logic:** A classic, simple moving average crossover strategy. It triggers a signal on the exact day the fast moving average (14) crosses above or below the slow moving average (28).
* **Signal Output:** 🟢 `LONG Crossover` or 🔴 `SHORT Crossunder`

---

## 💡 Pro-Tips & Troubleshooting

* **Rate Limits:** The scanner uses TradingView's free data feed (`tvDatafeed`). To prevent your IP address from getting blocked, the scanner intentionally pauses for 1.0 second between each batch of stocks. Allow the progress bar to finish completely.
* **"No Data" Errors:** Occasionally, TradingView may drop the connection or a ticker symbol in your custom CSV might be invalid. Ensure your Indian stock tickers do *not* have `.NS` or `.BO` attached in your CSV file (e.g., use `RELIANCE`, not `RELIANCE.NS`), as the engine handles the exchange routing automatically.
* **Market Context Matters:** A scanner finds structural setups; it does not read the news or the broader index trend. Always check the Nifty 50 trend before taking aggressive long positions, even if the scanner gives you a 🔥 `PRO SETUP`.