# RUC + rego — iPhone app (PWA + backend)

An "Add to Home Screen" web app for your iPhone that:

- **Buys RUC** — type the odometer, tap Buy; the server fills NZTA's form and pays.
- **Renews rego** — pick a 3/6/12-month period, tap Renew.
- **Shows WoF / rego / RUC expiry** — a colour-coded status panel (green → red).
- **Reminds you** before WoF or rego is due — by **email** and/or **iPhone push**.

Your card and plate live **only on the server**.

## Endpoints

| Route | Does |
|-------|------|
| `GET /api/status` | WoF / rego / RUC expiry dates (cached 6h) |
| `POST /api/purchase` | Buy RUC (price-capped) |
| `POST /api/renew-rego` | Renew rego / vehicle licence (price-capped) |

```
iPhone (PWA)  ──HTTPS──►  this backend (FastAPI + Playwright)  ──►  NZTA website
  odometer + token            fills form, checks total,
                              pays if under your cap
```

## Why a server?

iPhones can't run headless-browser automation. So the phone is just the
front-end; the actual form-filling runs here. You chose a **small cloud server**
so it works from anywhere, even when your computer is off.

## 1. Get a server

Any cheap Linux VPS works (1 vCPU / 1 GB is plenty). You need a **domain name**
pointing at it, because the PWA and your stored card both require **HTTPS**.

## 2. Configure

```bash
cp config.example.json config.json     # gitignored
python -c "import secrets; print(secrets.token_urlsafe(32))"   # make a token
```

Edit `config.json`: paste the token, your plate/vehicle type, email, **card
details**, and `max_charge_nzd` safety caps (one for RUC, one under `rego`).
Keep this file private.

**Email reminders (optional).** Leave the `smtp` block blank and you still get
the in-app status panel. Fill it in (host, from, your `reminders.email_to`, and
for Gmail an App Password) to also get a daily email when WoF or rego is within
`warn_days` / `second_warn_days` of expiry. A `reminder_state.json` file (gitignored)
remembers what's already been sent so you aren't spammed; it resets automatically
once you renew.

**iPhone push reminders (optional).** Generate a VAPID key pair and paste it into
the `vapid` block:

```bash
python make_vapid.py     # prints public_key / private_key / subject to paste
```

Then on your iPhone, open the installed app and tap **Enable reminders on this
iPhone** (push only works once the app is added to the Home Screen — iOS 16.4+).
Reminders then arrive as native notifications even with the app closed. Email and
push can both be on; each threshold notifies once.

## 3. Run it

**Docker (recommended):**
```bash
# build from the ruc/ directory so the shared core is included
cd ..                      # into ruc/
docker build -f server/Dockerfile -t ruc-app .
docker run -d --restart unless-stopped -p 127.0.0.1:8000:8000 \
  -v "$PWD/server/config.json:/app/server/config.json:ro" --name ruc ruc-app
```

**Or bare metal:**
```bash
pip install -r requirements.txt
python -m playwright install --with-deps chromium
python make_icons.py
python app.py
```

## 4. Put HTTPS in front

Terminate TLS with Caddy (easiest — auto certificates) or nginx + Let's Encrypt.
Example Caddyfile:

```
ruc.yourdomain.nz {
    reverse_proxy 127.0.0.1:8000
}
```

## 5. Install on your iPhone

1. Open `https://ruc.yourdomain.nz` in **Safari**.
2. Share → **Add to Home Screen**. A teal "RUC" icon appears.
3. Open it, paste your token once (stored on the phone only), and you're set:
   type the odometer, pick distance, tap **Buy**.

## Safety rails built in

- **Token-gated.** Every request needs your bearer token; without it the API
  returns 401.
- **Price cap.** The server reads NZTA's real order total and **refuses to pay**
  if it exceeds `max_charge_nzd` — protects against a fat-fingered unit count or
  a rate change.
- **Refuses to pay blind.** If it can't read the total, it aborts rather than
  guessing.
- **Card never touches the phone.** Only the server stores it.

## Verify the NZTA locators before trusting it

NZTA blocks automated access, so the form locators can't be checked from a
sandbox/CI box — and verifying a *purchase* would cost real money. Verify on your
own machine with the included harness, which opens each page visibly and **never
pays**:

```bash
cd ..                       # into ruc/
python verify.py            # expiry (runs fully, it's free) + ruc + rego (stop at payment)
python verify.py expiry     # just the free lookup
```

Each check reports PASS/FAIL per field and where it stopped, so any locator that
needs updating in `purchase_core.py` is obvious. The rego URL was confirmed
against NZTA's online-services listing; the per-field locators are best-effort
until you run this.

## Caveats (same as the CLI)

- Unofficial; drives the public NZTA form, which can change and break the
  locators (you'll get a clear "stuck at step X" error — fix it in
  `../purchase_core.py`, shared with the CLI).
- Anti-bot/CAPTCHA on NZTA may occasionally block a headless run; if that
  becomes frequent, the CLI (visible browser) is the fallback.
- You still display the emailed temporary label, and the odometer you enter must
  be accurate.
