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
# VERIFY: free expiry lookup (WoF / rego / RUC) by plate, no login required.
CHECK_EXPIRY_URL = "https://transact.nzta.govt.nz/transactions/CheckExpiry/entry"
# VERIFY: online rego (vehicle licensing) renewal entry point.
REGO_RENEWAL_URL = "https://transact.nzta.govt.nz/v2/renew-vehicle-licence"


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


# ---------------------------------------------------------------------------
# Expiry lookup (WoF / rego / RUC) and rego renewal
# ---------------------------------------------------------------------------

# Matches "14 Aug 2026", "14 August 2026", or "14/08/2026".
_DATE_RE = re.compile(
    r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}"
    r"|\d{1,2}/\d{1,2}/\d{4})",
    re.IGNORECASE,
)

# Page wording -> the key we report it under. First keyword that appears on a
# line claims the date found on that line.
_EXPIRY_LABELS = (
    ("warrant of fitness", "wof"),
    ("wof", "wof"),
    ("inspection", "wof"),
    ("licence", "rego"),      # vehicle licensing == "rego"
    ("licensing", "rego"),
    ("registration", "rego"),
    ("road user", "ruc"),
    ("ruc", "ruc"),
)


def check_expiry(page, plate: str) -> dict:
    """Look up WoF / rego / RUC expiry dates for a plate.

    Returns a dict like {"wof": "14 Aug 2026", "rego": "...", "ruc": "...",
    "raw": "<page text>"}. Missing keys mean that date wasn't found on the page.
    Scrapes visible text rather than fixed selectors, so it survives most layout
    changes; if NZTA renames things, update _EXPIRY_LABELS.
    """
    _step("open the expiry check page",
          lambda: page.goto(CHECK_EXPIRY_URL, wait_until="domcontentloaded"))
    _step("enter plate number",
          lambda: page.get_by_label("plate", exact=False).first.fill(plate))
    _step("submit the expiry lookup", lambda: _submit_lookup(page))

    try:
        page.wait_for_load_state("networkidle")
        text = page.inner_text("body")
    except Exception:  # noqa: BLE001
        text = ""

    result: dict[str, str] = {"raw": text}
    for line in text.splitlines():
        low = line.lower()
        date_match = _DATE_RE.search(line)
        if not date_match:
            continue
        for keyword, key in _EXPIRY_LABELS:
            if keyword in low and key not in result:
                result[key] = date_match.group(1)
                break
    return result


def _submit_lookup(page) -> None:
    for name in ("Check", "Search", "Continue", "Submit"):
        btn = page.get_by_role("button", name=name, exact=False)
        if btn.count() > 0:
            btn.first.click()
            return
    raise RuntimeError("could not find the submit button on the expiry lookup")


def fill_rego_form(page, cfg: dict, months: int) -> None:
    """Open the rego renewal page and fill it through to the payment screen.

    Like fill_purchase_form, stops at payment; the caller decides whether to pay.
    """
    vehicle = cfg["vehicle"]

    _step("open the rego renewal page",
          lambda: page.goto(REGO_RENEWAL_URL, wait_until="domcontentloaded"))
    _step("enter plate number",
          lambda: page.get_by_label("plate", exact=False).first.fill(vehicle["plate"]))
    _step("continue to licence options",
          lambda: page.get_by_role("button", name="Continue", exact=False).first.click())
    _step("select licence period",
          lambda: _select_rego_period(page, months))
    if cfg.get("purchase", {}).get("email"):
        _step("enter email for the licence",
              lambda: _fill_if_present(page, "email", cfg["purchase"]["email"]))
    _step("continue to payment",
          lambda: page.get_by_role("button", name="Continue", exact=False).first.click())


def _select_rego_period(page, months: int) -> None:
    """Pick the 3 / 6 / 12 month licence option, however the page presents it."""
    label = f"{months} month"
    # Try a radio/option first, then a dropdown.
    option = page.get_by_label(label, exact=False)
    if option.count() > 0:
        option.first.check()
        return
    radio = page.get_by_role("radio", name=label, exact=False)
    if radio.count() > 0:
        radio.first.check()
        return
    select = page.get_by_label("period", exact=False)
    if select.count() > 0:
        select.first.select_option(label=label)
        return
    raise RuntimeError(f"could not find a {label} licence option")
