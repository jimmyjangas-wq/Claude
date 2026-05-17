"""Life Organizer — track every renewal, repair and bill in one place.

A Streamlit app that keeps every recurring obligation in your life (insurance,
boat/car repairs, servicing, warrants of fitness, registration, bills) in one
dashboard. It tells you what's overdue, what's coming up, how much it all costs
per year, and rolls recurring items forward automatically when you tick them
off. Export everything to your phone calendar so reminders fire on their own.
"""

import os
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from dateutil.relativedelta import relativedelta
from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, Integer, MetaData, String, Table,
    Text, create_engine, delete, insert, select, update,
)
from sqlalchemy.engine import Engine

DEFAULT_SQLITE_URL = f"sqlite:///{Path(__file__).parent / 'life.db'}"

ASSET_KINDS = ["Car", "Boat", "Motorbike", "Caravan / Trailer", "Home", "Other"]
CATEGORIES = [
    "Insurance", "Warrant of Fitness", "Registration", "Service / Maintenance",
    "Repair", "Subscription / Bill", "Other",
]
RECURRENCES = {
    "one-off": None,
    "weekly": relativedelta(weeks=1),
    "fortnightly": relativedelta(weeks=2),
    "monthly": relativedelta(months=1),
    "quarterly": relativedelta(months=3),
    "6-monthly": relativedelta(months=6),
    "annual": relativedelta(years=1),
}
OCCURRENCES_PER_YEAR = {
    "weekly": 52, "fortnightly": 26, "monthly": 12,
    "quarterly": 4, "6-monthly": 2, "annual": 1,
}
RRULE = {
    "weekly": "FREQ=WEEKLY",
    "fortnightly": "FREQ=WEEKLY;INTERVAL=2",
    "monthly": "FREQ=MONTHLY",
    "quarterly": "FREQ=MONTHLY;INTERVAL=3",
    "6-monthly": "FREQ=MONTHLY;INTERVAL=6",
    "annual": "FREQ=YEARLY",
}


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------

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

_assets = Table(
    "assets", _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(128), nullable=False),
    Column("kind", String(32), nullable=False),
    Column("identifier", String(128)),
    Column("notes", Text),
    Column("created_at", DateTime, nullable=False),
)

_obligations = Table(
    "obligations", _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("asset_id", Integer),
    Column("category", String(48), nullable=False),
    Column("title", String(256), nullable=False),
    Column("provider", String(128)),
    Column("due_date", Date, nullable=False),
    Column("recurrence", String(24), nullable=False, default="one-off"),
    Column("cost", Float),
    Column("notes", Text),
    Column("last_completed", Date),
    Column("active", Boolean, nullable=False, default=True),
    Column("created_at", DateTime, nullable=False),
)


@st.cache_resource
def get_engine() -> Engine:
    engine = create_engine(_database_url(), future=True)
    _metadata.create_all(engine)
    return engine


def db_backend_label() -> str:
    return get_engine().url.get_backend_name()


def add_asset(name: str, kind: str, identifier: str, notes: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(insert(_assets).values(
            name=name, kind=kind, identifier=identifier or None,
            notes=notes or None, created_at=datetime.utcnow(),
        ))


def update_asset(asset_id: int, **fields) -> None:
    with get_engine().begin() as conn:
        conn.execute(update(_assets).where(_assets.c.id == asset_id).values(**fields))


def delete_asset(asset_id: int) -> None:
    with get_engine().begin() as conn:
        conn.execute(update(_obligations)
                     .where(_obligations.c.asset_id == asset_id)
                     .values(asset_id=None))
        conn.execute(delete(_assets).where(_assets.c.id == asset_id))


def load_assets() -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(select(_assets).order_by(_assets.c.name), conn)


def add_obligation(**fields) -> None:
    with get_engine().begin() as conn:
        conn.execute(insert(_obligations).values(
            active=True, created_at=datetime.utcnow(), **fields,
        ))


def update_obligation(obligation_id: int, **fields) -> None:
    with get_engine().begin() as conn:
        conn.execute(update(_obligations)
                     .where(_obligations.c.id == obligation_id)
                     .values(**fields))


def delete_obligation(obligation_id: int) -> None:
    with get_engine().begin() as conn:
        conn.execute(delete(_obligations).where(_obligations.c.id == obligation_id))


def load_obligations(include_archived: bool = False) -> pd.DataFrame:
    stmt = select(_obligations)
    if not include_archived:
        stmt = stmt.where(_obligations.c.active.is_(True))
    with get_engine().connect() as conn:
        df = pd.read_sql(stmt.order_by(_obligations.c.due_date), conn)
    if not df.empty:
        df["due_date"] = pd.to_datetime(df["due_date"]).dt.date
        df["last_completed"] = pd.to_datetime(df["last_completed"]).dt.date
    return df


# --------------------------------------------------------------------------
# Logic
# --------------------------------------------------------------------------

def next_due(due: date, recurrence: str) -> date | None:
    """Roll a due date forward by one recurrence interval, skipping past today."""
    delta = RECURRENCES.get(recurrence)
    if delta is None:
        return None
    nd = due + delta
    today = date.today()
    while nd <= today:
        nd += delta
    return nd


def complete_obligation(row: pd.Series) -> None:
    """Tick an obligation off. Recurring items roll forward; one-offs archive."""
    nd = next_due(row["due_date"], row["recurrence"])
    if nd is not None:
        update_obligation(int(row["id"]), due_date=nd, last_completed=date.today())
    else:
        update_obligation(int(row["id"]), active=False, last_completed=date.today())


def status_of(due: date) -> str:
    days = (due - date.today()).days
    if days < 0:
        return "Overdue"
    if days <= 7:
        return "Due this week"
    if days <= 30:
        return "Due this month"
    return "Upcoming"


STATUS_ICON = {
    "Overdue": "🔴", "Due this week": "🟠",
    "Due this month": "🟡", "Upcoming": "🟢",
}


def annualised_cost(df: pd.DataFrame) -> float:
    total = 0.0
    for _, row in df.iterrows():
        if pd.isna(row.get("cost")):
            continue
        per_year = OCCURRENCES_PER_YEAR.get(row["recurrence"])
        if per_year:
            total += float(row["cost"]) * per_year
    return total


def enrich(df: pd.DataFrame, assets: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["days_left"] = df["due_date"].map(lambda d: (d - date.today()).days)
    df["status"] = df["due_date"].map(status_of)
    asset_names = dict(zip(assets["id"], assets["name"])) if not assets.empty else {}
    df["asset_name"] = df["asset_id"].map(
        lambda a: asset_names.get(a, "—") if pd.notna(a) else "—")
    return df.sort_values("due_date")


# --------------------------------------------------------------------------
# Calendar export
# --------------------------------------------------------------------------

def _ics_escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;")
                .replace(",", "\\,").replace("\n", "\\n"))


def build_ics(df: pd.DataFrame, assets: pd.DataFrame) -> str:
    asset_names = dict(zip(assets["id"], assets["name"])) if not assets.empty else {}
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//Life Organizer//EN", "CALSCALE:GREGORIAN",
    ]
    for _, row in df.iterrows():
        d = row["due_date"]
        summary = row["title"]
        asset = asset_names.get(row["asset_id"]) if pd.notna(row["asset_id"]) else None
        if asset:
            summary = f"{summary} ({asset})"
        desc_bits = [f"Category: {row['category']}"]
        if pd.notna(row.get("provider")) and row["provider"]:
            desc_bits.append(f"Provider: {row['provider']}")
        if pd.notna(row.get("cost")):
            desc_bits.append(f"Est. cost: ${float(row['cost']):,.2f}")
        if pd.notna(row.get("notes")) and row["notes"]:
            desc_bits.append(str(row["notes"]))
        lines += [
            "BEGIN:VEVENT",
            f"UID:obligation-{row['id']}@life-organizer",
            f"DTSTAMP:{now}",
            f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}",
            f"SUMMARY:{_ics_escape(summary)}",
            f"DESCRIPTION:{_ics_escape(' — '.join(desc_bits))}",
        ]
        rule = RRULE.get(row["recurrence"])
        if rule:
            lines.append(f"RRULE:{rule}")
        lines += [
            "BEGIN:VALARM", "ACTION:DISPLAY",
            f"DESCRIPTION:{_ics_escape(summary)} is coming up",
            "TRIGGER:-P7D", "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------

def _money(v) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"${float(v):,.2f}"


def obligation_form(assets: pd.DataFrame, existing: pd.Series | None = None) -> None:
    """Render an add/edit form. If `existing` is given, edits that row."""
    is_edit = existing is not None
    key = f"edit-{existing['id']}" if is_edit else "add"
    asset_opts = ["(none)"] + (list(assets["name"]) if not assets.empty else [])
    asset_ids = [None] + (list(assets["id"]) if not assets.empty else [])

    with st.form(key=f"form-{key}"):
        c1, c2 = st.columns(2)
        title = c1.text_input("Title", value=existing["title"] if is_edit else "")
        category = c2.selectbox(
            "Category", CATEGORIES,
            index=CATEGORIES.index(existing["category"]) if is_edit
            and existing["category"] in CATEGORIES else 0)

        c3, c4 = st.columns(2)
        cur_asset = 0
        if is_edit and pd.notna(existing["asset_id"]) and existing["asset_id"] in asset_ids:
            cur_asset = asset_ids.index(existing["asset_id"])
        asset_pick = c3.selectbox("Asset", asset_opts, index=cur_asset)
        provider = c4.text_input(
            "Provider / company",
            value=existing["provider"] if is_edit and pd.notna(existing["provider"]) else "")

        c5, c6, c7 = st.columns(3)
        due = c5.date_input(
            "Next due date",
            value=existing["due_date"] if is_edit else date.today())
        rec_keys = list(RECURRENCES.keys())
        recurrence = c6.selectbox(
            "Repeats", rec_keys,
            index=rec_keys.index(existing["recurrence"]) if is_edit
            and existing["recurrence"] in rec_keys else 0)
        cost = c7.number_input(
            "Estimated cost ($)", min_value=0.0, step=10.0,
            value=float(existing["cost"]) if is_edit and pd.notna(existing["cost"]) else 0.0)

        notes = st.text_area(
            "Notes", value=existing["notes"] if is_edit and pd.notna(existing["notes"]) else "")

        submitted = st.form_submit_button(
            "Save changes" if is_edit else "Add item", type="primary")
        if submitted:
            if not title.strip():
                st.error("Title is required.")
                return
            picked_id = asset_ids[asset_opts.index(asset_pick)]
            fields = dict(
                asset_id=picked_id, category=category, title=title.strip(),
                provider=provider.strip() or None, due_date=due,
                recurrence=recurrence, cost=cost or None,
                notes=notes.strip() or None,
            )
            if is_edit:
                update_obligation(int(existing["id"]), **fields)
                st.success("Updated.")
            else:
                add_obligation(**fields)
                st.success(f"Added “{title.strip()}”.")
            st.rerun()


def render_dashboard(df: pd.DataFrame, assets: pd.DataFrame) -> None:
    st.subheader("Everything you need to stay on top of")
    if df.empty:
        st.info("Nothing tracked yet. Add your first item in the **Items** tab — "
                "or an asset (car, boat, home) in the **Assets** tab.")
        return

    overdue = df[df["status"] == "Overdue"]
    week = df[df["status"] == "Due this week"]
    month = df[df["status"] == "Due this month"]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Overdue", len(overdue))
    m2.metric("Due this week", len(week))
    m3.metric("Due this month", len(month))
    m4.metric("Annual recurring cost", _money(annualised_cost(df)))

    def section(title: str, subset: pd.DataFrame) -> None:
        if subset.empty:
            return
        st.markdown(f"#### {title}")
        for _, row in subset.iterrows():
            cols = st.columns([5, 2, 2, 2])
            label = f"{STATUS_ICON[row['status']]} **{row['title']}**"
            if row["asset_name"] != "—":
                label += f" · {row['asset_name']}"
            cols[0].markdown(f"{label}\n\n_{row['category']}_")
            days = row["days_left"]
            when = (f"{-days}d overdue" if days < 0
                    else "due today" if days == 0 else f"in {days}d")
            cols[1].markdown(f"{row['due_date']}\n\n_{when}_")
            cols[2].markdown(f"{_money(row['cost'])}\n\n_{row['recurrence']}_")
            if cols[3].button("Mark done", key=f"done-{row['id']}"):
                complete_obligation(row)
                st.rerun()
        st.divider()

    section("🔴 Overdue — handle these now", overdue)
    section("🟠 Due this week", week)
    section("🟡 Due this month", month)
    section("🟢 Coming up later", df[df["status"] == "Upcoming"])


def render_items(df: pd.DataFrame, assets: pd.DataFrame) -> None:
    with st.expander("➕ Add a new item", expanded=df.empty):
        obligation_form(assets)

    if df.empty:
        return

    st.markdown("#### Tracked items")
    view = df[["status", "title", "category", "asset_name", "due_date",
               "recurrence", "cost", "provider"]].copy()
    view["cost"] = view["cost"].map(_money)
    view.columns = ["Status", "Title", "Category", "Asset", "Due",
                    "Repeats", "Cost", "Provider"]
    st.dataframe(view, use_container_width=True, hide_index=True)

    st.markdown("#### Edit / complete / delete")
    for _, row in df.iterrows():
        head = (f"{STATUS_ICON[row['status']]} {row['title']} · "
                f"{row['category']} · due {row['due_date']}")
        with st.expander(head):
            obligation_form(assets, existing=row)
            c1, c2 = st.columns(2)
            if c1.button("✓ Mark done", key=f"item-done-{row['id']}"):
                complete_obligation(row)
                st.rerun()
            if c2.button("🗑 Delete", key=f"item-del-{row['id']}"):
                delete_obligation(int(row["id"]))
                st.rerun()


def render_assets(assets: pd.DataFrame, df: pd.DataFrame) -> None:
    with st.expander("➕ Add an asset", expanded=assets.empty):
        with st.form("add-asset"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Name", placeholder="e.g. Toyota Hilux")
            kind = c2.selectbox("Type", ASSET_KINDS)
            identifier = st.text_input(
                "Identifier", placeholder="Rego / VIN / hull number (optional)")
            notes = st.text_area("Notes")
            if st.form_submit_button("Add asset", type="primary"):
                if not name.strip():
                    st.error("Name is required.")
                else:
                    add_asset(name.strip(), kind, identifier.strip(), notes.strip())
                    st.success(f"Added {name.strip()}.")
                    st.rerun()

    if assets.empty:
        st.info("No assets yet. Add your car, boat or home above, then attach "
                "insurance, repairs and warrants to it.")
        return

    counts = df["asset_id"].value_counts() if not df.empty else {}
    for _, row in assets.iterrows():
        n = int(counts.get(row["id"], 0)) if not df.empty else 0
        with st.expander(f"{row['name']} · {row['kind']} · {n} item(s)"):
            with st.form(f"edit-asset-{row['id']}"):
                c1, c2 = st.columns(2)
                name = c1.text_input("Name", value=row["name"])
                kind = c2.selectbox(
                    "Type", ASSET_KINDS, index=ASSET_KINDS.index(row["kind"])
                    if row["kind"] in ASSET_KINDS else 0)
                identifier = st.text_input(
                    "Identifier", value=row["identifier"] or "")
                notes = st.text_area("Notes", value=row["notes"] or "")
                if st.form_submit_button("Save", type="primary"):
                    update_asset(int(row["id"]), name=name.strip(), kind=kind,
                                 identifier=identifier.strip() or None,
                                 notes=notes.strip() or None)
                    st.success("Saved.")
                    st.rerun()
            if st.button("🗑 Delete asset", key=f"asset-del-{row['id']}"):
                delete_asset(int(row["id"]))
                st.rerun()


def render_calendar(df: pd.DataFrame, assets: pd.DataFrame) -> None:
    st.markdown("#### Export to your phone calendar")
    st.write(
        "Download a calendar file and import it into Google Calendar, Apple "
        "Calendar or Outlook. Recurring items repeat automatically and each "
        "event reminds you **7 days before** — so the reminders run themselves."
    )
    if df.empty:
        st.info("Add some items first.")
        return
    st.download_button(
        "Download calendar (.ics)",
        data=build_ics(df, assets).encode("utf-8"),
        file_name=f"life_organizer_{date.today():%Y%m%d}.ics",
        mime="text/calendar",
        type="primary",
    )
    st.download_button(
        "Download all items (.csv)",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"life_organizer_{date.today():%Y%m%d}.csv",
        mime="text/csv",
    )

    st.divider()
    st.markdown("#### Timeline")
    timeline = df[["due_date", "title", "category", "asset_name", "status"]].copy()
    timeline.columns = ["Due", "Title", "Category", "Asset", "Status"]
    st.dataframe(timeline, use_container_width=True, hide_index=True)


def main() -> None:
    st.set_page_config(page_title="Life Organizer", page_icon="🗂", layout="wide")
    st.title("🗂 Life Organizer")
    st.caption(
        "Insurance, boat & car repairs, servicing, warrants, registration, "
        "bills — every renewal in one place, rolled forward automatically."
    )

    assets = load_assets()
    raw = load_obligations()
    df = enrich(raw, assets)

    dash, items, asset_tab, cal = st.tabs(
        ["Dashboard", "Items", "Assets", "Calendar & export"])

    with dash:
        render_dashboard(df, assets)
    with items:
        render_items(df, assets)
    with asset_tab:
        render_assets(assets, raw)
    with cal:
        render_calendar(df, assets)

    st.caption(
        f"Storage: **{db_backend_label()}** · "
        "Tick an item off and recurring obligations advance to their next due "
        "date on their own. This app organises and reminds — it can't sign "
        "contracts or pay bills for you."
    )


if __name__ == "__main__":
    main()
