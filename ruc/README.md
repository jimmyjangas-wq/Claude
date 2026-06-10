# RUC top-up (semi-automated, personal use)

A small Playwright script that drives NZTA's **Buy road user charges** web form
for a New Zealand light vehicle. It fills your saved vehicle profile, asks for
your current odometer reading, picks how much distance to buy, and takes you to
the payment page.

**It does not charge your card unless you pass `--pay`.** The default run fills
everything and stops at the payment screen so you can check the amount first.

This is the "one-click pay" / **Option A** design: you still supply the odometer
each time (type it, or read it off a photo), so it's *semi*-automated — seconds
of effort instead of minutes. Fully hands-off would require an automatic
odometer feed (OBD-II dongle), which is what commercial eRUC providers do.

## Setup

```bash
pip install -r requirements.txt
python -m playwright install chromium

cp config.example.json config.json   # then edit config.json with your details
```

`config.json` is **gitignored** and never committed. It holds your plate, email,
and (optionally) card details.

## Use

```bash
python buy_ruc.py                 # prompts for odometer, stops at payment to review
python buy_ruc.py --odometer 84210
python buy_ruc.py --units 2       # buy 2000 km this run
python buy_ruc.py --pay           # actually submit payment (only once you trust it)
```

A real Chrome window opens so you can watch (set `"headless": true` in config to
hide it). It pauses at the end until you press Enter, so you can finish anything
by hand.

## What you need to provide

NZTA's form needs more than just plate + card. Per top-up it requires:

1. **Plate** — static, from config.
2. **RUC vehicle type + weight** — static, from config (NZTA often pre-fills
   these from the plate, in which case the script skips them).
3. **Current odometer reading** — *the bit you supply each run.* This is why
   "plate + card only, fully automatic" isn't possible: the licence is issued as
   a distance band starting from your current odometer.
4. **Distance** — sold in 1000 km units for light vehicles.
5. **Card + email** — email receives the temporary label to print/display.

## Card handling

- Leave the `payment` fields in `config.json` blank → the script fills the form
  and **stops** so you type the card by hand. Safest.
- Fill them in → the script also auto-fills the card, but still won't submit
  unless you pass `--pay`. Storing a card in the file is your own risk; it's
  gitignored.

## Important caveats

- **Unofficial.** This automates a public web form for your own vehicle. NZTA
  doesn't offer a public buy-RUC API today (that's coming with the 2026–27 open
  RUC reforms), so this drives the website directly.
- **The page can change.** NZTA can redesign the form at any time, which may
  break the field locators. The script uses label-based locators and gives a
  clear "stuck at step X — update this locator" message when that happens. To
  capture fresh selectors:
  `python -m playwright codegen https://transact.nzta.govt.nz/v2/purchase-ruc`
- **Bot protection.** The transact site sits behind anti-bot measures. A real
  local Chrome (what this uses) normally gets through, but you may hit the odd
  CAPTCHA — just solve it in the open window.
- **You still display the label.** A DIY online purchase isn't display-exempt
  the way commercial electronic RUC is; the temporary label is emailed to you.
- **Accuracy is on you.** Enter the real odometer — an inaccurate reading is a
  compliance problem.

If you want true zero-effort, an OBD-II-fed version (Option B) or a commercial
eRUC subscription (EROAD AutoRUC, Cartrack) is the cleaner route.
