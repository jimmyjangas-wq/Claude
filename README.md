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
- **Saved ideas** — click "Save this idea" after analyzing to persist a snapshot. The "Saved ideas" tab lists everything with delete buttons and a **Download CSV** button.

## Storage

By default ideas are saved to a local SQLite file (`ideas.db`, gitignored). To use Postgres instead, set a `DATABASE_URL` env var (or add it to `.streamlit/secrets.toml`):

```bash
export DATABASE_URL=postgresql://user:pass@host:5432/dbname
streamlit run app.py
```

`postgres://` URLs are accepted and rewritten to `postgresql://` automatically. The `ideas` table is created on first run.

Educational use only, not investment advice.
