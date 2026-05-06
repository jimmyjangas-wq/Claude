"""Client Risk Analyzer.

Streamlit tool to research existing and potential clients, score payment risk
across financial / engagement / external dimensions, and recommend mitigation
terms drawn from a user-curated list of pre-agreed payment options.
"""

import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, MetaData, String, Table, Text,
    create_engine, delete, insert, select,
)
from sqlalchemy.engine import Engine

DEFAULT_SQLITE_URL = f"sqlite:///{Path(__file__).parent / 'clients.db'}"


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
_clients_table = Table(
    "client_profiles",
    _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("saved_at", DateTime, nullable=False),
    Column("client_name", String(256), nullable=False),
    Column("industry", String(128)),
    Column("country", String(128)),
    Column("years_in_business", Integer),
    Column("annual_revenue", Float),
    Column("employee_count", Integer),
    Column("relationship", String(32)),
    Column("contract_value", Float),
    Column("contract_duration_months", Integer),
    Column("credit_rating", String(32)),
    Column("late_payments", Integer),
    Column("avg_days_to_pay", Integer),
    Column("public_litigation", Boolean),
    Column("scope_clarity", Integer),
    Column("communication", Integer),
    Column("decision_maker_engaged", Boolean),
    Column("has_references", Boolean),
    Column("regulated_industry", Boolean),
    Column("cross_border", Boolean),
    Column("currency_volatility", Boolean),
    Column("notes", Text),
    Column("risk_score", Float),
    Column("risk_label", String(32)),
    Column("financial_score", Float),
    Column("engagement_score", Float),
    Column("external_score", Float),
    Column("recommended_terms", Text),
    Column("rationale", Text),
)


@st.cache_resource
def get_engine() -> Engine:
    engine = create_engine(_database_url(), future=True)
    _metadata.create_all(engine)
    return engine


def db_backend_label() -> str:
    return get_engine().url.get_backend_name()


# ---------- Risk scoring ----------

CREDIT_RATING_MAP = {
    "AAA": 1.00, "AA": 0.95, "A": 0.85, "BBB": 0.70, "BB": 0.50,
    "B": 0.35, "CCC": 0.20, "CC": 0.10, "C": 0.05, "D": 0.00,
    "Unknown / unrated": 0.40,
}

# Sectors with historically higher receivables risk (UK/US insolvency stats).
HIGH_RISK_INDUSTRIES = {
    "Construction", "Hospitality", "Retail", "Travel", "Restaurants",
    "Crypto / Web3",
}

PRESET_INDUSTRIES = [
    "Software / SaaS", "Financial services", "Healthcare", "Manufacturing",
    "Professional services", "Retail", "Hospitality", "Construction",
    "Travel", "Restaurants", "Crypto / Web3", "Public sector", "Education",
    "Media", "Other",
]


def _weighted(parts: list[tuple[float, float]]) -> float:
    if not parts:
        return 0.5
    total_w = sum(w for _, w in parts)
    return sum(v * w for v, w in parts) / total_w if total_w else 0.5


def score_financial(c: dict) -> tuple[float, list[str]]:
    notes: list[str] = []
    parts: list[tuple[float, float]] = []

    cr = c.get("credit_rating") or "Unknown / unrated"
    cr_score = CREDIT_RATING_MAP.get(cr, 0.4)
    parts.append((cr_score, 2.0))
    notes.append(f"Credit rating: {cr}")

    if c.get("relationship") == "Existing client":
        late = int(c.get("late_payments") or 0)
        if late == 0:
            parts.append((1.0, 1.5)); notes.append("No history of late payments")
        elif late <= 2:
            parts.append((0.6, 1.5)); notes.append(f"{late} late payment(s) on record")
        else:
            parts.append((0.2, 1.5)); notes.append(f"{late} late payments — recurring pattern")

        days = int(c.get("avg_days_to_pay") or 30)
        if days <= 14:
            parts.append((1.0, 1.0)); notes.append(f"Avg days to pay: {days} (fast)")
        elif days <= 30:
            parts.append((0.8, 1.0)); notes.append(f"Avg days to pay: {days}")
        elif days <= 60:
            parts.append((0.4, 1.0)); notes.append(f"Avg days to pay: {days} (slow)")
        else:
            parts.append((0.1, 1.0)); notes.append(f"Avg days to pay: {days} (very slow)")
    else:
        notes.append("No payment history (new / former client)")

    if c.get("public_litigation"):
        parts.append((0.2, 1.0)); notes.append("Public litigation, CCJs, or insolvency filings")
    else:
        parts.append((0.9, 0.5))

    yrs = int(c.get("years_in_business") or 0)
    if yrs >= 10:
        parts.append((1.0, 1.0)); notes.append(f"Established business ({yrs}y trading)")
    elif yrs >= 3:
        parts.append((0.7, 1.0)); notes.append(f"Trading {yrs}y")
    elif yrs >= 1:
        parts.append((0.4, 1.0)); notes.append(f"Young business ({yrs}y trading)")
    else:
        parts.append((0.2, 1.0)); notes.append("Less than 1 year trading")

    rev = c.get("annual_revenue")
    cv = c.get("contract_value")
    if rev and cv:
        ratio = cv / rev
        if ratio < 0.05:
            parts.append((1.0, 1.0))
            notes.append(f"Contract is {ratio:.1%} of client revenue (low concentration)")
        elif ratio < 0.20:
            parts.append((0.7, 1.0))
            notes.append(f"Contract is {ratio:.0%} of client revenue")
        else:
            parts.append((0.3, 1.0))
            notes.append(f"Contract is {ratio:.0%} of client revenue (affordability risk)")

    return _weighted(parts), notes


def score_engagement(c: dict) -> tuple[float, list[str]]:
    notes: list[str] = []
    parts: list[tuple[float, float]] = []

    sc = int(c.get("scope_clarity") or 3)
    parts.append((sc / 5, 1.5)); notes.append(f"Scope clarity: {sc}/5")

    cm = int(c.get("communication") or 3)
    parts.append((cm / 5, 1.0)); notes.append(f"Communication quality: {cm}/5")

    if c.get("decision_maker_engaged"):
        parts.append((1.0, 1.0)); notes.append("Decision-maker is engaged")
    else:
        parts.append((0.3, 1.0)); notes.append("Decision-maker not directly engaged")

    if c.get("has_references"):
        parts.append((1.0, 0.5)); notes.append("Verifiable references / case studies")
    else:
        parts.append((0.5, 0.5)); notes.append("No references provided")

    return _weighted(parts), notes


def score_external(c: dict) -> tuple[float, list[str]]:
    notes: list[str] = []
    parts: list[tuple[float, float]] = []

    industry = c.get("industry") or "Other"
    if industry in HIGH_RISK_INDUSTRIES:
        parts.append((0.4, 1.0))
        notes.append(f"Sector: {industry} (historically higher default rate)")
    else:
        parts.append((0.85, 1.0)); notes.append(f"Sector: {industry}")

    if c.get("regulated_industry"):
        parts.append((0.7, 0.5)); notes.append("Regulated industry — payment cycles can stretch")
    else:
        parts.append((1.0, 0.5))

    if c.get("cross_border"):
        parts.append((0.5, 1.0)); notes.append("Cross-border engagement — collection harder")
    else:
        parts.append((1.0, 1.0))

    if c.get("currency_volatility"):
        parts.append((0.4, 0.75)); notes.append("Material currency / FX exposure")
    else:
        parts.append((1.0, 0.5))

    return _weighted(parts), notes


def overall_risk(financial: float, engagement: float, external: float) -> tuple[float, str]:
    composite_health = financial * 0.5 + engagement * 0.25 + external * 0.25
    risk_pct = (1 - composite_health) * 100
    if risk_pct < 20:
        label = "LOW"
    elif risk_pct < 40:
        label = "MODERATE"
    elif risk_pct < 60:
        label = "HIGH"
    else:
        label = "CRITICAL"
    return risk_pct, label


# ---------- Mitigation engine ----------

PAYMENT_OPTIONS = [
    "100% upfront before work begins",
    "50% deposit, 50% on completion",
    "25% deposit + milestone-based invoicing",
    "Escrow (3rd-party held funds)",
    "Letter of credit (cross-border)",
    "Bank guarantee",
    "Monthly retainer (fixed, in advance)",
    "Net 7 invoicing",
    "Net 14 invoicing",
    "Net 30 invoicing",
    "Direct debit / standing order",
    "Credit card kept on file (auto-charge)",
    "Trade credit insurance",
    "Personal guarantee from director",
    "Stage gates — pause work if invoice unpaid",
    "Cap on work-in-progress exposure",
    "Late payment clause (statutory rate + admin fee)",
    "Right to suspend service / revoke licences",
]

DEFAULT_AVAILABLE = {
    "100% upfront before work begins",
    "50% deposit, 50% on completion",
    "25% deposit + milestone-based invoicing",
    "Net 14 invoicing",
    "Net 30 invoicing",
    "Direct debit / standing order",
    "Late payment clause (statutory rate + admin fee)",
    "Stage gates — pause work if invoice unpaid",
    "Cap on work-in-progress exposure",
    "Personal guarantee from director",
    "Escrow (3rd-party held funds)",
    "Letter of credit (cross-border)",
    "Trade credit insurance",
    "Right to suspend service / revoke licences",
}


def recommend_terms(risk_pct: float, c: dict, available: set[str]) -> tuple[list[str], list[str]]:
    """Pick a tailored set of pre-agreed terms based on risk level + signals."""
    rec: list[str] = []
    rationale: list[str] = []

    def add(term: str, why: str) -> None:
        if term in available and term not in rec:
            rec.append(term)
            rationale.append(f"{term} — {why}")

    if risk_pct >= 60:
        add("100% upfront before work begins",
            "critical risk profile makes deferred payment unsafe")
        add("Escrow (3rd-party held funds)",
            "if upfront is unacceptable to client, escrow protects both sides")
        add("Personal guarantee from director",
            "company-only liability is too thin at this risk level")
        add("Stage gates — pause work if invoice unpaid",
            "limit downside if any early payment slips")
        add("Right to suspend service / revoke licences",
            "fastest economic lever if payment stops")
    elif risk_pct >= 40:
        add("50% deposit, 50% on completion",
            "secures cash before work-in-progress builds up")
        add("25% deposit + milestone-based invoicing",
            "alternative for larger / longer engagements")
        add("Cap on work-in-progress exposure",
            "limits total unpaid exposure at any moment")
        add("Stage gates — pause work if invoice unpaid",
            "discipline if a milestone slips")
        add("Late payment clause (statutory rate + admin fee)",
            "creates economic incentive to pay on time")
        if c.get("relationship") == "New prospect":
            add("Trade credit insurance",
                "covers default risk for a counterparty without payment history")
    elif risk_pct >= 20:
        add("25% deposit + milestone-based invoicing",
            "small commitment up front aligns incentives")
        add("Net 14 invoicing",
            "tighter than market default of Net 30")
        add("Direct debit / standing order",
            "removes the manual approval step on the client side")
        add("Late payment clause (statutory rate + admin fee)",
            "standard protection at minimal friction")
    else:
        add("Net 30 invoicing",
            "low risk — market-standard terms acceptable")
        add("Direct debit / standing order",
            "reduces friction for both sides")
        add("Late payment clause (statutory rate + admin fee)",
            "standard protection")

    if c.get("cross_border"):
        add("Letter of credit (cross-border)",
            "secures payment across jurisdictions where collection is harder")

    cv = c.get("contract_value") or 0
    if cv >= 50_000:
        add("Stage gates — pause work if invoice unpaid",
            "high contract value warrants strict gating")
        add("Cap on work-in-progress exposure",
            "limit unpaid exposure on a large engagement")

    if not c.get("decision_maker_engaged"):
        add("Personal guarantee from director",
            "without an engaged decision-maker, company-only liability is risky")

    if c.get("contract_duration_months", 0) >= 6:
        add("Monthly retainer (fixed, in advance)",
            "long engagement: bill predictably in advance instead of in arrears")

    return rec, rationale


# ---------- Persistence ----------

def save_profile(c: dict, fin: float, eng: float, ext: float,
                 risk_pct: float, risk_label: str,
                 recs: list[str], rationale: list[str]) -> None:
    with get_engine().begin() as conn:
        conn.execute(insert(_clients_table).values(
            saved_at=datetime.utcnow(),
            client_name=c["client_name"],
            industry=c.get("industry"),
            country=c.get("country"),
            years_in_business=c.get("years_in_business"),
            annual_revenue=c.get("annual_revenue"),
            employee_count=c.get("employee_count"),
            relationship=c.get("relationship"),
            contract_value=c.get("contract_value"),
            contract_duration_months=c.get("contract_duration_months"),
            credit_rating=c.get("credit_rating"),
            late_payments=c.get("late_payments"),
            avg_days_to_pay=c.get("avg_days_to_pay"),
            public_litigation=bool(c.get("public_litigation")),
            scope_clarity=c.get("scope_clarity"),
            communication=c.get("communication"),
            decision_maker_engaged=bool(c.get("decision_maker_engaged")),
            has_references=bool(c.get("has_references")),
            regulated_industry=bool(c.get("regulated_industry")),
            cross_border=bool(c.get("cross_border")),
            currency_volatility=bool(c.get("currency_volatility")),
            notes=c.get("notes", ""),
            risk_score=risk_pct,
            risk_label=risk_label,
            financial_score=fin,
            engagement_score=eng,
            external_score=ext,
            recommended_terms="\n".join(recs),
            rationale="\n".join(rationale),
        ))


def load_profiles() -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(
            select(_clients_table).order_by(_clients_table.c.saved_at.desc()),
            conn,
        )


def delete_profile(idea_id: int) -> None:
    with get_engine().begin() as conn:
        conn.execute(delete(_clients_table).where(_clients_table.c.id == idea_id))


# ---------- UI ----------

def _collect_form() -> dict:
    st.markdown("#### 1. Client basics")
    a, b, c = st.columns(3)
    name = a.text_input("Client name *")
    industry = b.selectbox("Industry", PRESET_INDUSTRIES, index=0)
    country = c.text_input("Country / jurisdiction", "United Kingdom")

    a, b, c = st.columns(3)
    yrs = a.number_input("Years in business", 0, 200, 5)
    rev = b.number_input("Annual revenue", 0, 10**10, 0, step=1000,
                         help="Best estimate. Leave 0 if unknown.")
    emp = c.number_input("Employees", 0, 10**6, 0)

    relationship = st.radio(
        "Relationship",
        ["New prospect", "Existing client", "Former client"],
        horizontal=True,
    )

    st.markdown("#### 2. Engagement")
    a, b = st.columns(2)
    cv = a.number_input("Contract value", 0, 10**9, 10000, step=500)
    cd = b.number_input("Duration (months)", 0, 120, 3)

    st.markdown("#### 3. Financial signals")
    a, b, c = st.columns(3)
    cr = a.selectbox("Credit rating", list(CREDIT_RATING_MAP.keys()),
                     index=len(CREDIT_RATING_MAP) - 1,
                     help="From a credit reference agency, or 'Unknown' if not pulled.")
    late = b.number_input("Past late payments", 0, 100, 0,
                          help="Existing clients only — count of invoices paid late.")
    days = c.number_input("Avg days to pay", 0, 365, 30,
                          help="Existing clients only — typical days from invoice to payment.")

    a, b = st.columns(2)
    public_lit = a.checkbox(
        "Public litigation, CCJs, or insolvency filings",
        help="Anything found in Companies House / court records / press.",
    )
    regulated = b.checkbox("Operates in a regulated industry (NHS, financial services, etc.)")

    st.markdown("#### 4. Engagement quality")
    a, b = st.columns(2)
    scope = a.slider("Scope clarity (1=vague, 5=tight SOW)", 1, 5, 3)
    comm = b.slider("Communication quality (1=patchy, 5=excellent)", 1, 5, 3)

    a, b = st.columns(2)
    dm = a.checkbox("Decision-maker is engaged in conversations", value=True)
    refs = b.checkbox("Verifiable references / case studies available")

    st.markdown("#### 5. External factors")
    a, b = st.columns(2)
    cross = a.checkbox("Cross-border engagement")
    fx = b.checkbox("Material currency / FX volatility")

    notes = st.text_area(
        "Research notes",
        height=140,
        placeholder="Public sources, news, calls, anything relevant to risk…",
    )

    return {
        "client_name": name.strip(),
        "industry": industry,
        "country": country.strip(),
        "years_in_business": yrs,
        "annual_revenue": rev or None,
        "employee_count": emp or None,
        "relationship": relationship,
        "contract_value": cv,
        "contract_duration_months": cd,
        "credit_rating": cr,
        "late_payments": late,
        "avg_days_to_pay": days,
        "public_litigation": public_lit,
        "regulated_industry": regulated,
        "scope_clarity": scope,
        "communication": comm,
        "decision_maker_engaged": dm,
        "has_references": refs,
        "cross_border": cross,
        "currency_volatility": fx,
        "notes": notes,
    }


_RISK_BADGE = {"LOW": "🟢", "MODERATE": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}


def render_analysis(c: dict, available: set[str]) -> None:
    fin, fin_notes = score_financial(c)
    eng, eng_notes = score_engagement(c)
    ext, ext_notes = score_external(c)
    risk_pct, risk_label = overall_risk(fin, eng, ext)
    recs, rationale = recommend_terms(risk_pct, c, available)

    st.subheader(f"{c['client_name']} — risk profile")
    cols = st.columns(4)
    cols[0].metric("Risk score", f"{risk_pct:.0f} / 100", risk_label)
    cols[1].metric("Financial health", f"{fin:.0%}")
    cols[2].metric("Engagement", f"{eng:.0%}")
    cols[3].metric("External", f"{ext:.0%}")

    st.markdown(f"### {_RISK_BADGE[risk_label]} {risk_label} risk")

    left, right = st.columns(2)
    with left:
        st.markdown("#### Risk factors")
        st.markdown("**Financial**")
        for n in fin_notes:
            st.write(f"• {n}")
        st.markdown("**Engagement**")
        for n in eng_notes:
            st.write(f"• {n}")
        st.markdown("**External**")
        for n in ext_notes:
            st.write(f"• {n}")

    with right:
        st.markdown("#### Recommended payment terms")
        if not recs:
            st.warning(
                "No matching pre-agreed options. Tick more in the sidebar."
            )
        else:
            for r in recs:
                st.success(f"✓ {r}")
            with st.expander("Why these terms?"):
                for line in rationale:
                    st.write(f"• {line}")

    if st.button("Save this profile", type="primary", key="save-profile"):
        save_profile(c, fin, eng, ext, risk_pct, risk_label, recs, rationale)
        st.success(f"Saved profile for {c['client_name']}.")


def render_analyze_tab(available: set[str]) -> None:
    with st.form("client_form", clear_on_submit=False):
        data = _collect_form()
        submitted = st.form_submit_button("Run risk analysis", type="primary")

    if submitted:
        if not data["client_name"]:
            st.error("Client name is required.")
            return
        st.session_state["last_analysis"] = data

    if "last_analysis" in st.session_state:
        st.divider()
        render_analysis(st.session_state["last_analysis"], available)


def render_saved_tab() -> None:
    st.caption(f"Storage backend: **{db_backend_label()}**")
    df = load_profiles()
    if df.empty:
        st.info("No saved profiles yet. Run an analysis and click **Save this profile**.")
        return

    summary = df[[
        "saved_at", "client_name", "industry", "relationship",
        "contract_value", "risk_score", "risk_label",
    ]].copy()
    summary["risk_score"] = summary["risk_score"].round(0).astype(int)
    summary["contract_value"] = summary["contract_value"].map(
        lambda v: f"{v:,.0f}" if pd.notna(v) else "—"
    )
    summary.columns = [
        "Saved (UTC)", "Client", "Industry", "Relationship",
        "Contract", "Risk", "Label",
    ]
    st.dataframe(summary, use_container_width=True, hide_index=True)

    st.download_button(
        "Download CSV",
        df.to_csv(index=False).encode("utf-8"),
        f"client_profiles_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
        "text/csv",
    )

    st.divider()
    st.markdown("#### Manage")
    for _, row in df.iterrows():
        header = (
            f"{row['client_name']} · {_RISK_BADGE.get(row['risk_label'], '')} "
            f"{row['risk_label']} ({int(row['risk_score'])}) · {row['saved_at']}"
        )
        with st.expander(header):
            st.write(
                f"**Industry:** {row['industry'] or '—'}  |  "
                f"**Country:** {row['country'] or '—'}  |  "
                f"**Relationship:** {row['relationship'] or '—'}"
            )
            st.write(
                f"**Contract:** {row['contract_value']:,.0f} over "
                f"{row['contract_duration_months'] or 0} mo  |  "
                f"**Credit rating:** {row['credit_rating'] or '—'}"
            )
            st.markdown("**Recommended terms:**")
            for line in (row["recommended_terms"] or "").split("\n"):
                if line:
                    st.write(f"• {line}")
            with st.expander("Rationale"):
                for line in (row["rationale"] or "").split("\n"):
                    if line:
                        st.caption(line)
            if row["notes"]:
                st.markdown("**Research notes:**")
                st.write(row["notes"])
            if st.button("Delete", key=f"del-{row['id']}"):
                delete_profile(int(row["id"]))
                st.rerun()


def render_sidebar() -> set[str]:
    st.sidebar.markdown("### Pre-agreed payment options")
    st.sidebar.caption(
        "Tick the terms your business has approved. Recommendations are drawn "
        "only from this list."
    )
    available: set[str] = set()
    for opt in PAYMENT_OPTIONS:
        checked = st.sidebar.checkbox(
            opt, value=(opt in DEFAULT_AVAILABLE), key=f"opt::{opt}"
        )
        if checked:
            available.add(opt)
    return available


def main() -> None:
    st.set_page_config(page_title="Client Risk Analyzer", layout="wide")
    st.title("Client Risk Analyzer")
    st.caption(
        "Research existing & potential clients, score payment risk, and pick "
        "mitigation terms from your pre-agreed options."
    )

    available = render_sidebar()
    analyse_tab, saved_tab = st.tabs(["Analyse", "Saved profiles"])
    with analyse_tab:
        render_analyze_tab(available)
    with saved_tab:
        render_saved_tab()


if __name__ == "__main__":
    main()
