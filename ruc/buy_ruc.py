#!/usr/bin/env python3
"""Semi-automated personal RUC top-up for New Zealand light vehicles (CLI).

Drives the NZTA "Buy road user charges" web form in a real Chrome window:
fills your saved vehicle profile, prompts for the current odometer reading,
selects how much distance to buy, and takes you to the payment page.

By design it does NOT charge your card unless you pass ``--pay``. The default
is a safe "fill everything and stop so I can check the amount" run.

For an iPhone / always-on version, see the server/ folder, which reuses the same
form logic from purchase_core.py.

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

from purchase_core import PURCHASE_URL, PurchaseError, fill_card, fill_purchase_form

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
        page = browser.new_context().new_page()

        try:
            fill_purchase_form(page, cfg, odometer, units)
        except PurchaseError as exc:
            print(f"\n{exc}")
            print(f"Re-run without --headless to watch, or capture selectors with:\n"
                  f"  python -m playwright codegen {PURCHASE_URL}")
            browser.close()
            sys.exit(1)

        if fill_card(page, cfg.get("payment", {})):
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
                print(f"Could not click Pay automatically: {exc}")
                print("Complete the payment manually in the open window.")
        else:
            print("\nForm is filled and waiting on the payment screen.")
            print("Review the amount, then click Pay yourself (or re-run with --pay).")

        input("Press Enter here when you're done to close the browser... ")
        browser.close()


if __name__ == "__main__":
    main()
