#!/usr/bin/env python3
"""Semi-automated personal RUC top-up for New Zealand light vehicles.

Drives the NZTA "Buy road user charges" web form in a real Chrome window:
fills your saved vehicle profile, prompts for the current odometer reading,
selects how much distance to buy, and takes you to the payment page.

By design it does NOT charge your card unless you pass ``--pay``. The default
is a safe "fill everything and stop so I can check the amount" run.

This is an unofficial personal tool. NZTA can change their page at any time,
which may break the field locators below — see VERIFY notes and README.

Usage:
    python buy_ruc.py                      # prompt for odometer, stop at payment
    python buy_ruc.py --odometer 84210     # supply odometer non-interactively
    python buy_ruc.py --units 2            # buy 2000 km this run
    python buy_ruc.py --pay                # actually submit payment (use with care)
    python buy_ruc.py --config myconf.json # use a non-default config file
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# transact.nzta.govt.nz is the live RUC purchase portal. This entry URL is
# correct as of writing; if NZTA moves it, update PURCHASE_URL.
PURCHASE_URL = "https://transact.nzta.govt.nz/v2/purchase-ruc"

HERE = Path(__file__).parent


def load_config(path: Path) -> dict:
    if not path.exists():
        sys.exit(
            f"Config file not found: {path}\n"
            f"Copy config.example.json to {path.name} and fill in your details."
        )
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        sys.exit(f"Could not parse {path}: {exc}")


def get_odometer(cli_value: int | None) -> int:
    """Return the current odometer reading, from CLI or an interactive prompt."""
    if cli_value is not None:
        return cli_value
    while True:
        raw = input("Current odometer reading (whole km, e.g. 84210): ").strip().replace(",", "")
        if raw.isdigit():
            return int(raw)
        print("  Please enter digits only.")


def fill_purchase(page, cfg: dict, odometer: int, units: int) -> None:
    """Walk the NZTA purchase form.

    Locators use get_by_label / get_by_role where possible because they are far
    more stable across site redesigns than CSS classes. Each step is wrapped so
    a changed page produces a clear, actionable error instead of a stack trace.

    VERIFY: On your first run, watch the browser. If a step can't find its field,
    the label text below probably needs to match NZTA's current wording. Update
    the string in the matching page.get_by_label(...) call.
    """
    vehicle = cfg["vehicle"]
    purchase = cfg["purchase"]

    def step(description: str, action):
        try:
            action()
        except Exception as exc:  # noqa: BLE001 - we want a friendly message
            raise SystemExit(
                f"\nStuck at step: {description}\n"
                f"  Underlying error: {exc}\n"
                f"  The NZTA page layout may have changed. Re-run without --headless,\n"
                f"  watch where it stops, and update the locator for this step in buy_ruc.py.\n"
                f"  Tip: `python -m playwright codegen {PURCHASE_URL}` records fresh selectors."
            ) from exc

    step(
        "open the RUC purchase page",
        lambda: page.goto(PURCHASE_URL, wait_until="domcontentloaded"),
    )

    step(
        "enter plate number",
        lambda: page.get_by_label("Plate", exact=False).first.fill(vehicle["plate"]),
    )

    # Vehicle type / weight are often pre-filled by NZTA from the plate. Only
    # set them if the config provides a value AND the control is present.
    if vehicle.get("ruc_vehicle_type"):
        step(
            "select RUC vehicle type",
            lambda: _select_if_present(page, "vehicle type", vehicle["ruc_vehicle_type"]),
        )
    if vehicle.get("ruc_weight"):
        step(
            "select RUC weight",
            lambda: _select_if_present(page, "weight", vehicle["ruc_weight"]),
        )

    step(
        "enter current odometer reading",
        lambda: page.get_by_label("odometer", exact=False).first.fill(str(odometer)),
    )

    # Distance for light vehicles is bought in 1000 km units. Some versions of
    # the form ask for kilometres, others for "units" - try km first, fall back.
    km = units * 1000
    step(
        "enter distance to buy",
        lambda: _fill_distance(page, km, units),
    )

    if purchase.get("email"):
        step(
            "enter email for the licence",
            lambda: _fill_if_present(page, "email", purchase["email"]),
        )

    step(
        "continue to payment",
        lambda: page.get_by_role("button", name="Continue", exact=False).first.click(),
    )


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


def fill_card(page, payment: dict) -> bool:
    """Auto-fill card fields if all are provided in config. Returns True if filled."""
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Semi-automated NZ RUC top-up.")
    parser.add_argument("--config", default=str(HERE / "config.json"),
                        help="Path to config JSON (default: ruc/config.json)")
    parser.add_argument("--odometer", type=int, default=None,
                        help="Current odometer reading in km (otherwise you're prompted)")
    parser.add_argument("--units", type=int, default=None,
                        help="Number of 1000 km units to buy (overrides config)")
    parser.add_argument("--pay", action="store_true",
                        help="Actually submit the payment. Without this the script "
                             "stops at the payment screen for you to review and confirm.")
    parser.add_argument("--headless", action="store_true",
                        help="Run without a visible window (overrides config)")
    args = parser.parse_args()

    cfg = load_config(Path(args.config))
    units = args.units if args.units is not None else cfg["purchase"].get("units", 1)
    odometer = get_odometer(args.odometer)
    headless = args.headless or cfg.get("options", {}).get("headless", False)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit(
            "Playwright is not installed. Run:\n"
            "  pip install -r ruc/requirements.txt\n"
            "  python -m playwright install chromium"
        )

    print(f"Buying {units * 1000} km of RUC for {cfg['vehicle']['plate']} "
          f"at odometer {odometer:,} km...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        fill_purchase(page, cfg, odometer, units)

        filled_card = fill_card(page, cfg.get("payment", {}))
        if filled_card:
            print("Card details auto-filled from config.")
        else:
            print("No card in config - enter your card on the payment screen.")

        if args.pay:
            print("Submitting payment (--pay was set)...")
            try:
                page.get_by_role("button", name="Pay", exact=False).first.click()
                page.wait_for_load_state("networkidle")
                print("Payment submitted. Check your email for the RUC licence/label.")
            except Exception as exc:  # noqa: BLE001
                print(f"Could not click the Pay button automatically: {exc}")
                print("Complete the payment manually in the open window.")
        else:
            print("\nForm is filled and waiting on the payment screen.")
            print("Review the amount, then click Pay yourself (or re-run with --pay).")

        input("Press Enter here when you're done to close the browser... ")
        browser.close()


if __name__ == "__main__":
    main()
