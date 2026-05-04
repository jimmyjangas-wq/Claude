import math
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
from sqlalchemy import (
    Column, DateTime, Float, Integer, MetaData, String, Table, Text,
    create_engine, delete, insert, select,
)
from sqlalchemy.engine import Engine

DEFAULT_SQLITE_URL = f"sqlite:///{Path(__file__).parent / 'ideas.db'}"


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        try:
            url = st.secrets.get("DATABASE_URL")  # type: ignore[attr-defined]
        except Exception:
            url = None
    if not url:
        return DEFAULT_SQLITE_URL
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


_metadata = MetaData()
_ideas_table = Table(
    "ideas",
    _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("saved_at", DateTime, nullable=False),
    Column("ticker", String(16), nullable=False),
    Column("name", String(256)),
    Column("price", Float),
    Column("recommendation", String(32)),
    Column("composite", Float),
    Column("fund_score", Float),
    Column("tech_score", Float),
    Column("sentiment_label", String(32)),
    Column("thesis", Text),
)


@st.cache_resource
def get_engine() -> Engine:
    engine = create_engine(_database_url(), future=True)
    _metadata.create_all(engine)
    return engine


def db_backend_label() -> str:
    return get_engine().url.get_backend_name()


def save_idea(payload: dict) -> None:
    with get_engine().begin() as conn:
        conn.execute(insert(_ideas_table).values(
            saved_at=datetime.utcnow(),
            ticker=payload["ticker"],
            name=payload.get("name"),
            price=payload.get("price"),
            recommendation=payload["recommendation"],
            composite=payload["composite"],
            fund_score=payload["fund_score"],
            tech_score=payload["tech_score"],
            sentiment_label=payload["sentiment_label"],
            thesis=payload.get("thesis", ""),
        ))


def load_ideas() -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(
            select(_ideas_table).order_by(_ideas_table.c.saved_at.desc()),
            conn,
        )


def delete_idea(idea_id: int) -> None:
    with get_engine().begin() as conn:
        conn.execute(delete(_ideas_table).where(_ideas_table.c.id == idea_id))


POSITIVE_WORDS = {
    "growth", "growing", "strong", "beat", "beats", "moat", "undervalued",
    "cheap", "bullish", "buy", "expand", "expanding", "innovative", "leader",
    "dominant", "profitable", "upside", "tailwind", "tailwinds", "accelerating",
    "outperform", "momentum", "breakout", "raise", "raised", "guidance",
    "dividend", "buyback", "buybacks", "record", "surge", "soar",
}
NEGATIVE_WORDS = {
    "decline", "declining", "weak", "miss", "misses", "overvalued", "expensive",
    "bearish", "sell", "shrink", "shrinking", "lawsuit", "fraud", "debt",
    "dilution", "downside", "headwind", "headwinds", "slowing", "underperform",
    "breakdown", "cut", "cuts", "warning", "loss", "losses", "drop", "plunge",
    "risk", "risks", "regulatory", "investigation",
}


def fetch_data(ticker: str):
    t = yf.Ticker(ticker)
    hist = t.history(period="2y", auto_adjust=True)
    info = {}
    try:
        info = t.info or {}
    except Exception:
        pass
    return hist, info


def rsi(series: pd.Series, period: int = 14) -> float:
    if len(series) < period + 1:
        return float("nan")
    delta = series.diff().dropna()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi_series = 100 - (100 / (1 + rs))
    return float(rsi_series.iloc[-1])


def compute_technicals(hist: pd.DataFrame) -> dict:
    close = hist["Close"].dropna()
    if close.empty:
        return {}
    last = float(close.iloc[-1])
    ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else float("nan")
    ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else float("nan")
    pct_52w_high = float(close.iloc[-252:].max()) if len(close) >= 1 else float("nan")
    pct_52w_low = float(close.iloc[-252:].min()) if len(close) >= 1 else float("nan")
    returns = close.pct_change().dropna()
    vol_annual = float(returns.std() * math.sqrt(252)) if not returns.empty else float("nan")
    return {
        "price": last,
        "ma50": ma50,
        "ma200": ma200,
        "above_ma50": last > ma50 if not math.isnan(ma50) else None,
        "above_ma200": last > ma200 if not math.isnan(ma200) else None,
        "golden_cross": (ma50 > ma200) if not (math.isnan(ma50) or math.isnan(ma200)) else None,
        "rsi14": rsi(close, 14),
        "high_52w": pct_52w_high,
        "low_52w": pct_52w_low,
        "from_52w_high_pct": (last / pct_52w_high - 1) * 100 if pct_52w_high else float("nan"),
        "vol_annualized_pct": vol_annual * 100 if not math.isnan(vol_annual) else float("nan"),
    }


def compute_fundamentals(info: dict) -> dict:
    def g(key):
        v = info.get(key)
        return v if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)) else None

    return {
        "name": info.get("longName") or info.get("shortName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "market_cap": g("marketCap"),
        "pe_trailing": g("trailingPE"),
        "pe_forward": g("forwardPE"),
        "peg": g("pegRatio"),
        "pb": g("priceToBook"),
        "ps": g("priceToSalesTrailing12Months"),
        "profit_margin": g("profitMargins"),
        "roe": g("returnOnEquity"),
        "revenue_growth": g("revenueGrowth"),
        "earnings_growth": g("earningsGrowth"),
        "debt_to_equity": g("debtToEquity"),
        "dividend_yield": g("dividendYield"),
        "beta": g("beta"),
        "summary": info.get("longBusinessSummary"),
    }


def sentiment_score(text: str) -> dict:
    if not text or not text.strip():
        return {"score": 0, "positive": 0, "negative": 0, "label": "n/a"}
    words = [w.strip(".,!?():;\"'").lower() for w in text.split()]
    pos = sum(1 for w in words if w in POSITIVE_WORDS)
    neg = sum(1 for w in words if w in NEGATIVE_WORDS)
    total = pos + neg
    if total == 0:
        return {"score": 0, "positive": 0, "negative": 0, "label": "neutral"}
    score = (pos - neg) / total
    if score > 0.25:
        label = "positive"
    elif score < -0.25:
        label = "negative"
    else:
        label = "mixed"
    return {"score": score, "positive": pos, "negative": neg, "label": label}


def score_fundamentals(f: dict) -> tuple[float, list[str]]:
    notes, points, max_points = [], 0.0, 0.0

    def add(condition_value, weight, good_msg, bad_msg, neutral_msg=None):
        nonlocal points, max_points
        max_points += weight
        if condition_value is True:
            points += weight
            notes.append(f"+ {good_msg}")
        elif condition_value is False:
            notes.append(f"- {bad_msg}")
        elif neutral_msg:
            notes.append(f"~ {neutral_msg}")

    pe = f.get("pe_forward") or f.get("pe_trailing")
    add(pe is not None and 0 < pe < 20, 1.5, f"P/E reasonable ({pe:.1f})" if pe else "",
        f"P/E elevated ({pe:.1f})" if pe else "P/E unavailable")

    peg = f.get("peg")
    add(peg is not None and 0 < peg < 1.5, 1.0, f"PEG attractive ({peg:.2f})" if peg else "",
        f"PEG high ({peg:.2f})" if peg else "PEG unavailable")

    rg = f.get("revenue_growth")
    add(rg is not None and rg > 0.10, 1.5, f"Revenue growth strong ({rg:.0%})" if rg is not None else "",
        f"Revenue growth weak ({rg:.0%})" if rg is not None else "Revenue growth unavailable")

    roe = f.get("roe")
    add(roe is not None and roe > 0.15, 1.0, f"ROE healthy ({roe:.0%})" if roe is not None else "",
        f"ROE low ({roe:.0%})" if roe is not None else "ROE unavailable")

    pm = f.get("profit_margin")
    add(pm is not None and pm > 0.10, 1.0, f"Profit margin solid ({pm:.0%})" if pm is not None else "",
        f"Profit margin thin ({pm:.0%})" if pm is not None else "Margin unavailable")

    de = f.get("debt_to_equity")
    add(de is not None and de < 100, 1.0, f"Debt/equity moderate ({de:.0f})" if de is not None else "",
        f"Debt/equity high ({de:.0f})" if de is not None else "Debt unavailable")

    return (points / max_points if max_points else 0), notes


def score_technicals(t: dict) -> tuple[float, list[str]]:
    notes, points, max_points = [], 0.0, 0.0

    def add(condition_value, weight, good_msg, bad_msg):
        nonlocal points, max_points
        max_points += weight
        if condition_value is True:
            points += weight
            notes.append(f"+ {good_msg}")
        elif condition_value is False:
            notes.append(f"- {bad_msg}")

    add(t.get("above_ma50"), 1.0, "Price above 50-day MA", "Price below 50-day MA")
    add(t.get("above_ma200"), 1.5, "Price above 200-day MA", "Price below 200-day MA")
    add(t.get("golden_cross"), 1.0, "50-day above 200-day (bullish trend)", "50-day below 200-day (bearish trend)")

    rsi_v = t.get("rsi14")
    if rsi_v is not None and not math.isnan(rsi_v):
        max_points += 1.0
        if 40 <= rsi_v <= 65:
            points += 1.0
            notes.append(f"+ RSI healthy ({rsi_v:.0f})")
        elif rsi_v > 70:
            notes.append(f"- RSI overbought ({rsi_v:.0f})")
        elif rsi_v < 30:
            notes.append(f"~ RSI oversold ({rsi_v:.0f}) — possible bounce")
            points += 0.5
        else:
            notes.append(f"~ RSI neutral ({rsi_v:.0f})")
            points += 0.5

    return (points / max_points if max_points else 0), notes


def overall_recommendation(fund_score: float, tech_score: float, sent: dict) -> tuple[str, float]:
    sent_norm = (sent["score"] + 1) / 2 if sent["label"] != "n/a" else 0.5
    weights = {"fund": 0.5, "tech": 0.35, "sent": 0.15}
    composite = fund_score * weights["fund"] + tech_score * weights["tech"] + sent_norm * weights["sent"]
    if composite >= 0.65:
        return "BUY", composite
    if composite >= 0.45:
        return "HOLD", composite
    return "SELL / AVOID", composite


def fmt(v, suffix="", pct=False, money=False):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    if pct:
        return f"{v * 100:.1f}%"
    if money:
        if v >= 1e12:
            return f"${v / 1e12:.2f}T"
        if v >= 1e9:
            return f"${v / 1e9:.2f}B"
        if v >= 1e6:
            return f"${v / 1e6:.2f}M"
        return f"${v:,.0f}"
    if isinstance(v, float):
        return f"{v:.2f}{suffix}"
    return f"{v}{suffix}"


def render_analysis(ticker: str, thesis: str) -> None:
    with st.spinner(f"Fetching {ticker}…"):
        try:
            hist, info = fetch_data(ticker)
        except Exception as e:
            st.error(f"Failed to fetch {ticker}: {e}")
            return

    if hist.empty:
        st.error(f"No price data for {ticker}.")
        return

    fundamentals = compute_fundamentals(info)
    technicals = compute_technicals(hist)
    sentiment = sentiment_score(thesis)
    fund_score, fund_notes = score_fundamentals(fundamentals)
    tech_score, tech_notes = score_technicals(technicals)
    rec, composite = overall_recommendation(fund_score, tech_score, sentiment)

    header = f"{fundamentals['name'] or ticker} ({ticker})"
    if fundamentals.get("sector"):
        header += f" — {fundamentals['sector']}"
    st.subheader(header)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Price", fmt(technicals.get("price"), money=True))
    c2.metric("Market cap", fmt(fundamentals.get("market_cap"), money=True))
    c3.metric("Composite score", f"{composite:.0%}")
    c4.metric("Recommendation", rec)

    if st.button("Save this idea", type="secondary"):
        save_idea({
            "ticker": ticker,
            "name": fundamentals.get("name"),
            "price": technicals.get("price"),
            "recommendation": rec,
            "composite": composite,
            "fund_score": fund_score,
            "tech_score": tech_score,
            "sentiment_label": sentiment["label"],
            "thesis": thesis,
        })
        st.success(f"Saved {ticker} to your ideas.")

    st.divider()
    left, right = st.columns([3, 2])

    with left:
        st.markdown("#### Price (2y)")
        st.line_chart(hist["Close"])

        st.markdown("#### Scorecard notes")
        st.markdown(f"**Fundamentals — {fund_score:.0%}**")
        for n in fund_notes:
            st.write(n)
        st.markdown(f"**Technicals — {tech_score:.0%}**")
        for n in tech_notes:
            st.write(n)
        st.markdown(f"**Thesis sentiment — {sentiment['label']}**")
        st.write(
            f"Positive words: {sentiment['positive']} · Negative words: {sentiment['negative']}"
        )

    with right:
        st.markdown("#### Fundamentals")
        st.table(pd.DataFrame({
            "Metric": [
                "P/E (trailing)", "P/E (forward)", "PEG", "P/B", "P/S",
                "Profit margin", "ROE", "Revenue growth", "Earnings growth",
                "Debt/Equity", "Dividend yield", "Beta",
            ],
            "Value": [
                fmt(fundamentals["pe_trailing"]),
                fmt(fundamentals["pe_forward"]),
                fmt(fundamentals["peg"]),
                fmt(fundamentals["pb"]),
                fmt(fundamentals["ps"]),
                fmt(fundamentals["profit_margin"], pct=True),
                fmt(fundamentals["roe"], pct=True),
                fmt(fundamentals["revenue_growth"], pct=True),
                fmt(fundamentals["earnings_growth"], pct=True),
                fmt(fundamentals["debt_to_equity"]),
                fmt(fundamentals["dividend_yield"], pct=True),
                fmt(fundamentals["beta"]),
            ],
        }))

        st.markdown("#### Technicals")
        st.table(pd.DataFrame({
            "Metric": [
                "50-day MA", "200-day MA", "RSI(14)",
                "52w high", "52w low", "From 52w high",
                "Annualized vol",
            ],
            "Value": [
                fmt(technicals.get("ma50")),
                fmt(technicals.get("ma200")),
                fmt(technicals.get("rsi14")),
                fmt(technicals.get("high_52w")),
                fmt(technicals.get("low_52w")),
                fmt(technicals.get("from_52w_high_pct"), suffix="%"),
                fmt(technicals.get("vol_annualized_pct"), suffix="%"),
            ],
        }))

    if fundamentals.get("summary"):
        with st.expander("Business summary"):
            st.write(fundamentals["summary"])

    st.caption(
        f"Data via yfinance · Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} · "
        "Educational use only, not investment advice."
    )


def render_saved_ideas() -> None:
    st.caption(f"Storage backend: **{db_backend_label()}**")
    df = load_ideas()
    if df.empty:
        st.info("No saved ideas yet. Analyze a ticker and click **Save this idea**.")
        return

    summary = df[[
        "saved_at", "ticker", "name", "price", "recommendation",
        "composite", "fund_score", "tech_score", "sentiment_label",
    ]].copy()
    summary["composite"] = (summary["composite"] * 100).round(0).astype(int).astype(str) + "%"
    summary["fund_score"] = (summary["fund_score"] * 100).round(0).astype(int).astype(str) + "%"
    summary["tech_score"] = (summary["tech_score"] * 100).round(0).astype(int).astype(str) + "%"
    summary["price"] = summary["price"].map(lambda v: f"${v:,.2f}" if pd.notna(v) else "—")
    summary.columns = [
        "Saved (UTC)", "Ticker", "Name", "Price", "Rec",
        "Composite", "Fund", "Tech", "Sentiment",
    ]
    st.dataframe(summary, use_container_width=True, hide_index=True)

    st.download_button(
        "Download CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"stock_ideas_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
    )

    st.divider()
    st.markdown("#### Manage")
    for _, row in df.iterrows():
        with st.expander(
            f"{row['ticker']} · {row['recommendation']} · {row['saved_at']}"
        ):
            st.write(f"**Name:** {row['name'] or '—'}")
            st.write(
                f"**Composite:** {row['composite']:.0%} · "
                f"**Fund:** {row['fund_score']:.0%} · "
                f"**Tech:** {row['tech_score']:.0%} · "
                f"**Sentiment:** {row['sentiment_label']}"
            )
            st.write("**Thesis:**")
            st.write(row["thesis"] or "_(none)_")
            if st.button("Delete", key=f"del-{row['id']}"):
                delete_idea(int(row["id"]))
                st.rerun()


def main():
    st.set_page_config(page_title="Stock Idea Analyzer", layout="wide")
    st.title("Stock Idea Analyzer")
    st.caption("Pulls live data, runs a fundamentals + technicals + sentiment scorecard.")

    with st.sidebar:
        ticker = st.text_input("Ticker", value="AAPL").strip().upper()
        thesis = st.text_area(
            "Your thesis (optional)",
            placeholder="Why do you like this stock? Risks?",
            height=180,
        )
        run = st.button("Analyze", type="primary", use_container_width=True)

    analyze_tab, saved_tab = st.tabs(["Analyze", "Saved ideas"])

    with analyze_tab:
        if run:
            if not ticker:
                st.error("Ticker is required.")
            else:
                render_analysis(ticker, thesis)
        else:
            st.info("Enter a ticker on the left and click **Analyze**.")

    with saved_tab:
        render_saved_ideas()


if __name__ == "__main__":
    main()
