# Deploying Life Organizer to a Hostinger VPS

These steps put the app on your VPS behind your own domain, with a password
prompt and HTTPS. Assumes Ubuntu 22.04 / 24.04 (Hostinger's default).

End result: open `https://life.yourdomain.com` on your phone, enter your
password, and your tracker is there. Add it to your home screen.

---

## 0. Before you start

You need:
- The VPS IP address (in hPanel → VPS)
- SSH access (root or sudo)
- A domain or subdomain you control. Point an **A record** at the VPS IP
  (e.g. `life.yourdomain.com` → your VPS IP). DNS can take a few minutes.

## 1. SSH into the VPS

```bash
ssh root@YOUR_VPS_IP
```

## 2. Install system packages

```bash
apt update && apt upgrade -y
apt install -y python3-venv python3-pip git nginx apache2-utils certbot python3-certbot-nginx
```

## 3. Create a dedicated user and clone the repo

```bash
adduser --system --group --home /opt/life-organizer lifeorg
cd /opt
git clone https://github.com/jimmyjangas-wq/claude.git life-organizer
cd life-organizer
git checkout claude/life-organization-tracker-DF9c7
chown -R lifeorg:lifeorg /opt/life-organizer
```

If the repo is private, use a deploy key or a personal access token in the URL:
`git clone https://USERNAME:TOKEN@github.com/jimmyjangas-wq/claude.git life-organizer`

## 4. Install Python dependencies in a virtualenv

```bash
sudo -u lifeorg python3 -m venv /opt/life-organizer/.venv
sudo -u lifeorg /opt/life-organizer/.venv/bin/pip install --upgrade pip
sudo -u lifeorg /opt/life-organizer/.venv/bin/pip install -r /opt/life-organizer/requirements.txt
```

## 5. Install and start the systemd service

```bash
cp /opt/life-organizer/deploy/life-organizer.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now life-organizer
systemctl status life-organizer    # should say "active (running)"
```

If it's not running:

```bash
journalctl -u life-organizer -n 50 --no-pager
```

The app is now listening on `127.0.0.1:8501` (not reachable from outside yet).

## 6. Set up nginx as a reverse proxy with password protection

Create the password file (you'll be prompted for a password):

```bash
htpasswd -c /etc/nginx/.htpasswd james
```

Configure nginx:

```bash
cp /opt/life-organizer/deploy/nginx.conf.example /etc/nginx/sites-available/life-organizer
sed -i "s/YOUR_DOMAIN/life.yourdomain.com/" /etc/nginx/sites-available/life-organizer
ln -s /etc/nginx/sites-available/life-organizer /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
```

At this point `http://life.yourdomain.com` should prompt for your password and
load the app. Confirm it does before moving on.

## 7. Add HTTPS (free, via Let's Encrypt)

```bash
certbot --nginx -d life.yourdomain.com --redirect --agree-tos -m you@yourdomain.com -n
```

Certbot edits the nginx config to add SSL and auto-renews itself.

## 8. Open it on your phone

Visit `https://life.yourdomain.com`, enter your password, and add the page to
your home screen:
- **iPhone (Safari):** Share button → "Add to Home Screen"
- **Android (Chrome):** ⋮ menu → "Add to Home screen"

It now opens like a native app.

---

## Where your data lives

By default the app uses SQLite — a single file at
`/opt/life-organizer/life.db`. It survives reboots and redeployments.

**Back it up** by copying that file off the server, e.g.:

```bash
scp root@YOUR_VPS_IP:/opt/life-organizer/life.db ~/life-backup-$(date +%F).db
```

Or add a daily cron job on the VPS that copies it to a backups directory.

If you'd prefer Postgres (multiple devices writing, or you want a managed DB):

```bash
apt install -y postgresql
sudo -u postgres createuser lifeorg
sudo -u postgres createdb -O lifeorg lifeorganizer
sudo -u postgres psql -c "ALTER USER lifeorg WITH PASSWORD 'CHANGE_ME';"
```

Then edit `/etc/systemd/system/life-organizer.service` and add under `[Service]`:

```
Environment="DATABASE_URL=postgresql://lifeorg:CHANGE_ME@localhost/lifeorganizer"
```

`systemctl daemon-reload && systemctl restart life-organizer`.

---

## Updating the app later

When you make changes (or I push new features):

```bash
cd /opt/life-organizer
sudo -u lifeorg git pull
sudo -u lifeorg /opt/life-organizer/.venv/bin/pip install -r requirements.txt
systemctl restart life-organizer
```

## Troubleshooting

- **App won't start:** `journalctl -u life-organizer -n 100 --no-pager`
- **502 Bad Gateway in browser:** the Streamlit service isn't running — check above.
- **Domain doesn't resolve:** confirm the A record points to your VPS IP
  (`dig +short life.yourdomain.com`).
- **Login prompt loops:** check `/etc/nginx/.htpasswd` exists and is readable
  by nginx (`chmod 644 /etc/nginx/.htpasswd`).
