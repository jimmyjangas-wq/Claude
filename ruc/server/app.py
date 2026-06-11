#!/usr/bin/env python3
"""Backend for the RUC / rego iPhone (PWA) app.

Serves a small mobile web app and exposes protected endpoints that run NZTA
transactions headless on the server:

  GET  /api/profile     - non-secret info for the UI
  GET  /api/status      - WoF / rego / RUC expiry dates (cached)
  POST /api/purchase    - buy RUC (price-capped)
  POST /api/renew-rego  - renew vehicle licence / rego (price-capped)

It also runs an optional daily job that emails WoF / rego reminders.

Your card and plate stay here; the phone only ever sends an odometer reading,
a unit/period count, and a shared token. Put this behind HTTPS in production.
"""

from __future__ import annotations

import hmac
import json
import smtplib
import sys
import threading
import time
from datetime import date, datetime
from email.message import EmailMessage
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from purchase_core import (  # noqa: E402
    PurchaseError,
    check_expiry,
    click_pay,
    fill_card,
    fill_purchase_form,
    fill_rego_form,
    read_total_nzd,
)

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
CONFIG_PATH = HERE / "config.json"
STATE_PATH = HERE / "reminder_state.json"

STATUS_TTL_SECONDS = 6 * 3600


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        sys.exit(
            f"Config not found: {CONFIG_PATH}\n"
            "Copy config.example.json to config.json and fill it in."
        )
    return json.loads(CONFIG_PATH.read_text())


CONFIG = load_config()

app = FastAPI(title="RUC / rego top-up")

# Simple in-memory cache for the expiry status (each lookup spins a browser).
_status_cache: dict = {"data": None, "ts": 0.0}


# ---------------------------------------------------------------------------
# Auth + helpers
# ---------------------------------------------------------------------------

def _check_auth(authorization: str | None) -> None:
    expected = CONFIG.get("api_token", "")
    if not expected or expected == "CHANGE-ME-to-a-long-random-string":
        raise HTTPException(500, "Server api_token is not configured.")
    token = authorization[7:] if authorization and authorization.lower().startswith("bearer ") else ""
    if not hmac.compare_digest(token, expected):
        raise HTTPException(401, "Bad or missing token.")


def _new_page(p):
    browser = p.chromium.launch(headless=CONFIG.get("options", {}).get("headless", True))
    return browser, browser.new_context().new_page()


def _require_card() -> dict:
    payment = CONFIG.get("payment", {})
    if not all(payment.get(k) for k in ("name_on_card", "card_number", "expiry", "cvc")):
        raise HTTPException(400, "Server has no card configured; cannot pay unattended.")
    return payment


def _pay_with_cap(page, max_charge: float) -> float:
    """Read the order total, enforce the cap, then pay. Returns the total."""
    total = read_total_nzd(page)
    if total is None:
        raise HTTPException(502, "Could not read the order total from NZTA; refusing to "
                                 "pay blind. Try again or use the CLI.")
    if max_charge and total > max_charge:
        raise HTTPException(409, f"Order total ${total:.2f} exceeds the cap ${max_charge:.2f}; "
                                 f"payment refused.")
    click_pay(page)
    return total


def parse_nz_date(value: str) -> date | None:
    value = value.strip()
    for fmt in ("%d %b %Y", "%d %B %Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _level(days: int | None, warn: int, second: int) -> str:
    if days is None:
        return "unknown"
    if days < 0:
        return "expired"
    if days <= second:
        return "urgent"
    if days <= warn:
        return "warn"
    return "ok"


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class PurchaseRequest(BaseModel):
    odometer: int = Field(..., ge=0)
    units: int = Field(1, ge=1, le=20)


class RegoRequest(BaseModel):
    months: int = Field(12, ge=1, le=12)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/profile")
def profile(authorization: str | None = Header(default=None)) -> dict:
    _check_auth(authorization)
    safety = CONFIG.get("safety", {})
    return {
        "plate": CONFIG["vehicle"]["plate"],
        "default_units": CONFIG["purchase"].get("units", 1),
        "estimate_per_unit_nzd": safety.get("estimate_per_unit_nzd"),
        "default_rego_months": CONFIG.get("rego", {}).get("months", 12),
    }


def _compute_status() -> dict:
    reminders = CONFIG.get("reminders", {})
    warn = int(reminders.get("warn_days", 21))
    second = int(reminders.get("second_warn_days", 7))
    plate = CONFIG["vehicle"]["plate"]

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise HTTPException(500, "Playwright not installed on the server.")

    with sync_playwright() as p:
        browser, page = _new_page(p)
        try:
            found = check_expiry(page, plate)
        except PurchaseError as exc:
            raise HTTPException(502, str(exc))
        finally:
            browser.close()

    items = []
    today = date.today()
    for key, label in (("wof", "Warrant of Fitness"), ("rego", "Registration (rego)"), ("ruc", "Road User Charges")):
        raw = found.get(key)
        parsed = parse_nz_date(raw) if raw else None
        days = (parsed - today).days if parsed else None
        items.append({
            "key": key,
            "label": label,
            "expiry": raw,
            "iso": parsed.isoformat() if parsed else None,
            "days_until": days,
            "level": _level(days, warn, second),
        })
    return {"plate": plate, "checked_at": datetime.now().isoformat(timespec="seconds"), "items": items}


@app.get("/api/status")
def status(refresh: int = 0, authorization: str | None = Header(default=None)) -> dict:
    _check_auth(authorization)
    now = time.time()
    if not refresh and _status_cache["data"] and now - _status_cache["ts"] < STATUS_TTL_SECONDS:
        return _status_cache["data"]
    data = _compute_status()
    _status_cache.update(data=data, ts=now)
    return data


@app.post("/api/purchase")
def purchase(req: PurchaseRequest, authorization: str | None = Header(default=None)) -> dict:
    _check_auth(authorization)
    payment = _require_card()
    max_charge = float(CONFIG.get("safety", {}).get("max_charge_nzd", 0) or 0)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise HTTPException(500, "Playwright not installed on the server.")

    with sync_playwright() as p:
        browser, page = _new_page(p)
        try:
            fill_purchase_form(page, CONFIG, req.odometer, req.units)
            fill_card(page, payment)
            total = _pay_with_cap(page, max_charge)
            return {
                "status": "ok",
                "total_nzd": total,
                "km": req.units * 1000,
                "message": f"Bought {req.units * 1000} km for ${total:.2f}. "
                           f"Check {CONFIG['purchase'].get('email', 'your email')} for the label.",
            }
        except PurchaseError as exc:
            raise HTTPException(502, str(exc))
        finally:
            browser.close()


@app.post("/api/renew-rego")
def renew_rego(req: RegoRequest, authorization: str | None = Header(default=None)) -> dict:
    _check_auth(authorization)
    payment = _require_card()
    max_charge = float(CONFIG.get("rego", {}).get("max_charge_nzd", 0) or 0)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise HTTPException(500, "Playwright not installed on the server.")

    with sync_playwright() as p:
        browser, page = _new_page(p)
        try:
            fill_rego_form(page, CONFIG, req.months)
            fill_card(page, payment)
            total = _pay_with_cap(page, max_charge)
            _status_cache.update(data=None, ts=0.0)  # expiry changed; force refresh
            return {
                "status": "ok",
                "total_nzd": total,
                "months": req.months,
                "message": f"Renewed rego for {req.months} months for ${total:.2f}. "
                           f"Check {CONFIG['purchase'].get('email', 'your email')} for the label.",
            }
        except PurchaseError as exc:
            raise HTTPException(502, str(exc))
        finally:
            browser.close()


# ---------------------------------------------------------------------------
# Email reminders (optional daily job)
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2))


def _smtp_configured() -> bool:
    s = CONFIG.get("smtp", {})
    return bool(s.get("host") and s.get("from") and CONFIG.get("reminders", {}).get("email_to"))


def _send_email(subject: str, body: str) -> None:
    s = CONFIG["smtp"]
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = s["from"]
    msg["To"] = CONFIG["reminders"]["email_to"]
    msg.set_content(body)
    with smtplib.SMTP(s["host"], int(s.get("port", 587))) as server:
        if s.get("use_tls", True):
            server.starttls()
        if s.get("username"):
            server.login(s["username"], s.get("password", ""))
        server.send_message(msg)


def _run_reminder_check() -> None:
    """Send a reminder per item that has newly crossed a warning threshold."""
    reminders = CONFIG.get("reminders", {})
    warn = int(reminders.get("warn_days", 21))
    second = int(reminders.get("second_warn_days", 7))
    try:
        data = _compute_status()
    except HTTPException as exc:
        print(f"[reminders] status lookup failed: {exc.detail}")
        return

    state = _load_state()
    state.setdefault("last_run", "")
    state["last_run"] = date.today().isoformat()

    for item in data["items"]:
        if item["key"] not in ("wof", "rego") or item["days_until"] is None:
            continue
        key = item["key"]
        entry = state.get(key, {})
        # Reset history if the expiry date changed (e.g. you renewed).
        if entry.get("iso") != item["iso"]:
            entry = {"iso": item["iso"], "sent": []}
        days = item["days_until"]
        threshold = None
        if days <= second:
            threshold = "second"
        elif days <= warn:
            threshold = "warn"
        if threshold and threshold not in entry["sent"]:
            when = "expired" if days < 0 else f"due in {days} day{'s' if days != 1 else ''}"
            subject = f"{item['label']} {when} - {data['plate']}"
            body = (f"{item['label']} for {data['plate']} expires {item['expiry']} ({when}).\n\n"
                    f"Open the RUC app to renew." if key == "rego"
                    else f"{item['label']} for {data['plate']} expires {item['expiry']} ({when}).\n\n"
                         f"Book a WoF inspection - it can't be renewed online.")
            try:
                _send_email(subject, body)
                entry["sent"].append(threshold)
                print(f"[reminders] emailed {key} ({when})")
            except Exception as exc:  # noqa: BLE001
                print(f"[reminders] email failed: {exc}")
        state[key] = entry

    _save_state(state)


def _reminder_loop() -> None:
    check_hour = int(CONFIG.get("reminders", {}).get("check_hour_local", 8))
    while True:
        now = datetime.now()
        state = _load_state()
        if now.hour == check_hour and state.get("last_run") != date.today().isoformat():
            _run_reminder_check()
        time.sleep(1800)  # re-check every 30 minutes


@app.on_event("startup")
def _start_reminders() -> None:
    if _smtp_configured():
        threading.Thread(target=_reminder_loop, daemon=True).start()
        print("[reminders] daily email reminders enabled")
    else:
        print("[reminders] email not configured - in-app status panel only")


# ---------------------------------------------------------------------------
# Static PWA (mounted last so /api/* wins)
# ---------------------------------------------------------------------------

@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/", StaticFiles(directory=STATIC), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
