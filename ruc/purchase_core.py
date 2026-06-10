"""Shared NZTA RUC purchase logic used by both the CLI and the web backend.

Keeping the fragile, page-specific locators in ONE place means the CLI tool and
the iPhone backend can never drift apart when NZTA changes their form.

I could not crawl the live transact.nzta.govt.nz page (it sits behind anti-bot
protection), so these locators are best-effort and label-based. When a step
can't find its field, callers get a clear "stuck at step X" message telling them
which locator to update. Capture fresh selectors with:
    python -m playwright codegen https://transact.nzta.govt.nz/v2/purchase-ruc
"""

from __future__ import annotations

import re

PURCHASE_URL = "https://transact.nzta.govt.nz/v2/purchase-ruc"


class PurchaseError(RuntimeError):
    """Raised with a human-friendly message when a form step fails."""


def _step(description: str, action):
    try:
        return action()
    except Exception as exc:  # noqa: BLE001 - convert to a friendly message
        raise PurchaseError(
            f"Stuck at step: {description}. The NZTA page layout may have "
            f"changed - update the locator for this step in purchase_core.py. "
            f"(underlying error: {exc})"
        ) from exc


def _select_if_present(page, label_fragment: str, value: str) -> None:
    loc = page.get_by_label(label_fragment, exact=False)
    if loc.count() == 0:
        return  # NZTA pre-filled it from the plate; nothing to do.
    loc.first.select_option(label=value)


def _fill_if_present(page, label_fragment: str, value: str) -> None:
    loc = page.get_by_label(label_fragment, exact=False)
    if loc.count() == 0:
        return
    loc.first.fill(value)


def _fill_distance(page, km: int, units: int) -> None:
    for label, value in (("distance", km), ("kilometres", km), ("units", units)):
        loc = page.get_by_label(label, exact=False)
        if loc.count() > 0:
            loc.first.fill(str(value))
            return
    raise RuntimeError("could not find a distance/units field on the page")


def fill_purchase_form(page, cfg: dict, odometer: int, units: int) -> None:
    """Open the purchase page and fill it through to the payment screen.

    Stops once the payment page is reached. Does not enter card details or pay -
    that is the caller's decision (the CLI pauses for review, the server applies
    a price cap before submitting).
    """
    vehicle = cfg["vehicle"]
    purchase = cfg["purchase"]
    km = units * 1000

    _step("open the RUC purchase page",
          lambda: page.goto(PURCHASE_URL, wait_until="domcontentloaded"))

    _step("enter plate number",
          lambda: page.get_by_label("Plate", exact=False).first.fill(vehicle["plate"]))

    if vehicle.get("ruc_vehicle_type"):
        _step("select RUC vehicle type",
              lambda: _select_if_present(page, "vehicle type", vehicle["ruc_vehicle_type"]))
    if vehicle.get("ruc_weight"):
        _step("select RUC weight",
              lambda: _select_if_present(page, "weight", vehicle["ruc_weight"]))

    _step("enter current odometer reading",
          lambda: page.get_by_label("odometer", exact=False).first.fill(str(odometer)))

    _step("enter distance to buy",
          lambda: _fill_distance(page, km, units))

    if purchase.get("email"):
        _step("enter email for the licence",
              lambda: _fill_if_present(page, "email", purchase["email"]))

    _step("continue to payment",
          lambda: page.get_by_role("button", name="Continue", exact=False).first.click())


def fill_card(page, payment: dict) -> bool:
    """Fill card fields if all are provided. Returns True if it filled them."""
    needed = ("name_on_card", "card_number", "expiry", "cvc")
    if not all(payment.get(k) for k in needed):
        return False
    mapping = {
        "name on card": payment["name_on_card"],
        "card number": payment["card_number"],
        "expiry": payment["expiry"],
        "cvc": payment["cvc"],
    }
    for label, value in mapping.items():
        loc = page.get_by_label(label, exact=False)
        if loc.count() > 0:
            loc.first.fill(value)
    return True


_AMOUNT_RE = re.compile(r"\$\s?([0-9]+(?:,[0-9]{3})*\.[0-9]{2})")


def read_total_nzd(page) -> float | None:
    """Best-effort scrape of the order total from the payment page.

    Returns the largest dollar amount on the page (the total incl. transaction
    fee is normally the biggest figure), or None if none found. Used as a safety
    check against a configured maximum before any payment is submitted.
    """
    try:
        text = page.inner_text("body")
    except Exception:  # noqa: BLE001
        return None
    amounts = [float(m.replace(",", "")) for m in _AMOUNT_RE.findall(text)]
    return max(amounts) if amounts else None


def click_pay(page) -> str:
    """Submit the payment and return a short status string (best-effort)."""
    page.get_by_role("button", name="Pay", exact=False).first.click()
    page.wait_for_load_state("networkidle")
    body = ""
    try:
        body = page.inner_text("body").lower()
    except Exception:  # noqa: BLE001
        pass
    if any(word in body for word in ("thank you", "confirmation", "receipt", "successful", "licence purchased")):
        return "success"
    return "submitted"
