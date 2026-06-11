#!/usr/bin/env python3
"""Verify the NZTA locators against the live site - safely.

Run this on YOUR machine (it needs a real browser and your plate). It opens each
NZTA page in a visible window and checks that the locators in purchase_core.py
still line up with the current site:

  * expiry  - runs the free WoF/rego/RUC lookup end to end and prints the dates
  * ruc     - fills the RUC form up to the payment page, then STOPS (no payment)
  * rego    - fills the rego form up to the payment page, then STOPS (no payment)

Nothing is ever paid. This is the verification step that can't be done from a
CI/sandbox box, because NZTA blocks automated access and a real purchase would
cost money on your plate.

Usage:
    python verify.py                 # run all checks
    python verify.py expiry          # just the free lookup
    python verify.py ruc --odometer 84210
    python verify.py rego --months 12
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from purchase_core import (
    PurchaseError,
    check_expiry,
    fill_purchase_form,
    fill_rego_form,
    read_total_nzd,
)

HERE = Path(__file__).parent


def load_config(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"Config not found: {path}. Copy config.example.json to config.json first.")
    return json.loads(path.read_text())


def _ok(msg: str) -> None:
    print(f"  \033[32mPASS\033[0m {msg}")


def _fail(msg: str) -> None:
    print(f"  \033[31mFAIL\033[0m {msg}")


def verify_expiry(page, cfg: dict) -> bool:
    print("\n[expiry] free WoF / rego / RUC lookup")
    try:
        found = check_expiry(page, cfg["vehicle"]["plate"])
    except PurchaseError as exc:
        _fail(str(exc))
        return False
    got_any = False
    for key in ("wof", "rego", "ruc"):
        if found.get(key):
            _ok(f"{key}: {found[key]}")
            got_any = True
        else:
            _fail(f"{key}: not found in page text")
    if not got_any:
        print("  Hint: open the page and check the wording in _EXPIRY_LABELS / _DATE_RE.")
    return got_any


def verify_form(page, cfg: dict, kind: str, odometer: int, months: int) -> bool:
    print(f"\n[{kind}] fill form up to payment (no payment will be made)")
    try:
        if kind == "ruc":
            fill_purchase_form(page, cfg, odometer, cfg["purchase"].get("units", 1))
        else:
            fill_rego_form(page, cfg, months)
    except PurchaseError as exc:
        _fail(str(exc))
        return False
    _ok("reached the payment page without locator errors")
    total = read_total_nzd(page)
    if total is not None:
        _ok(f"order total read back as ${total:.2f}")
    else:
        _fail("could not read an order total (read_total_nzd returned None)")
    print("  Review the open window, then close it. NOTHING was paid.")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify NZTA locators (no payments).")
    parser.add_argument("checks", nargs="*", default=["expiry", "ruc", "rego"],
                        choices=["expiry", "ruc", "rego"],
                        help="Which checks to run (default: all)")
    parser.add_argument("--config", default=str(HERE / "config.json"))
    parser.add_argument("--odometer", type=int, default=1, help="Odometer for the RUC check")
    parser.add_argument("--months", type=int, default=12, help="Period for the rego check")
    args = parser.parse_args()

    cfg = load_config(Path(args.config))
    checks = args.checks if args.checks else ["expiry", "ruc", "rego"]

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Install Playwright first: pip install -r requirements.txt && "
                 "python -m playwright install chromium")

    results: dict[str, bool] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # always visible for verification
        for check in checks:
            page = browser.new_context().new_page()
            if check == "expiry":
                results["expiry"] = verify_expiry(page, cfg)
            else:
                results[check] = verify_form(page, cfg, check, args.odometer, args.months)
            input(f"  Press Enter to continue (closing the {check} window)... ")
            page.context.close()
        browser.close()

    print("\nSummary:")
    for check, ok in results.items():
        print(f"  {check}: {'OK' if ok else 'needs a locator fix in purchase_core.py'}")
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()
