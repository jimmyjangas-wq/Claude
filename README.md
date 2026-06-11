# 🗂 Life Organizer

One dashboard for every renewal, repair and bill in your life — insurance, boat
and car repairs, servicing, warrants of fitness, registration, subscriptions.
It tells you what's overdue, what's coming up, how much it all costs per year,
and rolls recurring items forward automatically when you tick them off.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

Open the URL Streamlit prints (usually http://localhost:8501).

## What it does

- **Assets** — register your car, boat, home, motorbike, caravan, etc. (with
  rego / VIN / hull number) and attach obligations to them.
- **Items** — track any recurring or one-off obligation: category, provider,
  next due date, repeat interval, estimated cost and notes.
- **Dashboard** — at-a-glance counts of what's overdue, due this week, and due
  this month, plus your total **annual recurring cost**. Colour-coded and
  sorted by urgency.
- **Auto roll-forward** — tick an item **Mark done** and a recurring obligation
  advances to its next due date by itself (weekly → annual). One-off items are
  archived.
- **Calendar export** — download an `.ics` file and import it into Google /
  Apple / Outlook calendar. Recurring items repeat and each event reminds you
  **7 days early**, so reminders run on their own. CSV export too.

## Storage

By default everything is saved to a local SQLite file (`life.db`, gitignored).
To use Postgres instead, set a `DATABASE_URL` env var (or add it to
`.streamlit/secrets.toml`):

```bash
export DATABASE_URL=postgresql://user:pass@host:5432/dbname
streamlit run app.py
```

`postgres://` URLs are accepted and rewritten to `postgresql://` automatically.
Tables are created on first run.

## Deploy to your own server (Hostinger VPS)

For Hostinger's **Docker + Traefik** template (Ubuntu 24.04), see
[`deploy/DEPLOY.md`](deploy/DEPLOY.md): ship the included Dockerfile via
`docker compose up -d --build`, and Traefik handles HTTPS, routing and
password protection automatically.

## A note on "complete automation"

This app organises and reminds — it keeps everything in one place, tracks due
dates, advances recurring items, and feeds reminders into your calendar so you
don't have to remember anything. It can't legally sign contracts, book a
mechanic, or pay bills for you, so think of it as the system that makes sure
nothing is ever forgotten.
