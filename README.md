# Stock Idea Analyzer

A small Streamlit web app that pulls live market data and scores a stock idea on fundamentals, technicals, and the sentiment of your written thesis.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

Open the URL Streamlit prints (usually http://localhost:8501).

## What it does

- **Fundamentals** — P/E, PEG, margins, ROE, growth, debt, dividend (via `yfinance`).
- **Technicals** — 50/200-day moving averages, golden cross, RSI(14), 52-week range, volatility.
- **Sentiment** — counts positive/negative keywords in your written thesis.
- **Scorecard** — weighted composite (50% fundamentals, 35% technicals, 15% sentiment) → BUY / HOLD / SELL.

Educational use only, not investment advice.
