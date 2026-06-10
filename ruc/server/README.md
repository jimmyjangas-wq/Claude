# RUC top-up — iPhone app (PWA + backend)

An "Add to Home Screen" web app for your iPhone that buys NZ road user charges
for your vehicle. You type the odometer and tap **Buy**; the server fills NZTA's
form headless and pays. Your card and plate live **only on the server**.

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
details**, and a `max_charge_nzd` safety cap. Keep this file private.

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

## Caveats (same as the CLI)

- Unofficial; drives the public NZTA form, which can change and break the
  locators (you'll get a clear "stuck at step X" error — fix it in
  `../purchase_core.py`, shared with the CLI).
- Anti-bot/CAPTCHA on NZTA may occasionally block a headless run; if that
  becomes frequent, the CLI (visible browser) is the fallback.
- You still display the emailed temporary label, and the odometer you enter must
  be accurate.
