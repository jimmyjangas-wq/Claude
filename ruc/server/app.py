#!/usr/bin/env python3
"""Backend for the RUC iPhone (PWA) app.

Serves a small mobile web app and exposes one protected endpoint that runs the
NZTA purchase headless on the server. The phone only ever sends an odometer
reading and a unit count plus a shared token; your card and plate stay here.

Run locally:
    pip install -r requirements.txt
    python -m playwright install --with-deps chromium
    python app.py            # serves on http://0.0.0.0:8000

In production put this behind HTTPS (see README) - the PWA and your card both
require it.
"""

from __future__ import annotations

import hmac
import json
import sys
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Import the shared NZTA form logic from the parent ruc/ package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from purchase_core import (  # noqa: E402
    PurchaseError,
    click_pay,
    fill_card,
    fill_purchase_form,
    read_total_nzd,
)

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
CONFIG_PATH = HERE / "config.json"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        sys.exit(
            f"Config not found: {CONFIG_PATH}\n"
            "Copy config.example.json to config.json and fill it in."
        )
    return json.loads(CONFIG_PATH.read_text())


CONFIG = load_config()

app = FastAPI(title="RUC top-up")


class PurchaseRequest(BaseModel):
    odometer: int = Field(..., ge=0, description="Current odometer reading in km")
    units: int = Field(1, ge=1, le=20, description="Number of 1000 km units to buy")


def _check_auth(authorization: str | None) -> None:
    expected = CONFIG.get("api_token", "")
    if not expected or expected == "CHANGE-ME-to-a-long-random-string":
        raise HTTPException(500, "Server api_token is not configured.")
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:]
    if not hmac.compare_digest(token, expected):
        raise HTTPException(401, "Bad or missing token.")


@app.get("/api/profile")
def profile(authorization: str | None = Header(default=None)) -> dict:
    """Non-secret info the app needs to render: plate, default units, estimate."""
    _check_auth(authorization)
    safety = CONFIG.get("safety", {})
    return {
        "plate": CONFIG["vehicle"]["plate"],
        "default_units": CONFIG["purchase"].get("units", 1),
        "estimate_per_unit_nzd": safety.get("estimate_per_unit_nzd"),
        "max_charge_nzd": safety.get("max_charge_nzd"),
    }


@app.post("/api/purchase")
def purchase(req: PurchaseRequest, authorization: str | None = Header(default=None)) -> dict:
    """Fill the NZTA form headless, enforce the price cap, then pay.

    Defined as a sync function on purpose: FastAPI runs it in a worker thread, so
    Playwright's sync API is safe to use here without clashing with the event loop.
    """
    _check_auth(authorization)

    payment = CONFIG.get("payment", {})
    if not all(payment.get(k) for k in ("name_on_card", "card_number", "expiry", "cvc")):
        raise HTTPException(400, "Server has no card configured; cannot pay unattended.")

    max_charge = float(CONFIG.get("safety", {}).get("max_charge_nzd", 0) or 0)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise HTTPException(500, "Playwright not installed on the server.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=CONFIG.get("options", {}).get("headless", True))
        page = browser.new_context().new_page()
        try:
            fill_purchase_form(page, CONFIG, req.odometer, req.units)
            fill_card(page, payment)

            total = read_total_nzd(page)
            if total is None:
                raise HTTPException(502, "Could not read the order total from NZTA; "
                                         "refusing to pay blind. Try again or use the CLI.")
            if max_charge and total > max_charge:
                raise HTTPException(
                    409,
                    f"Order total ${total:.2f} exceeds your max_charge_nzd "
                    f"${max_charge:.2f}; payment refused.",
                )

            status = click_pay(page)
            return {
                "status": status,
                "total_nzd": total,
                "units": req.units,
                "km": req.units * 1000,
                "message": f"Bought {req.units * 1000} km for ${total:.2f}. "
                           f"Check {CONFIG['purchase'].get('email', 'your email')} for the label.",
            }
        except PurchaseError as exc:
            raise HTTPException(502, str(exc))
        finally:
            browser.close()


# Serve the PWA. Mounted last so /api/* routes take precedence.
@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/", StaticFiles(directory=STATIC), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
