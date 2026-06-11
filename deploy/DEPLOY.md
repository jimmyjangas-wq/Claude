# Deploying Life Organizer to a Hostinger VPS

For Hostinger's **Docker + Traefik** VPS template (Ubuntu 24.04). Traefik
handles HTTPS, routing, and password protection automatically — you just ship
the container with the right labels.

End result: open `https://life.yourdomain.com` on your phone, enter your
password, tracker is there. Add it to your home screen.

## 0. Before you start

- VPS IP from hPanel → VPS
- A domain or subdomain you control. Add an **A record** for the subdomain
  (e.g. `life.yourdomain.com`) pointing to your VPS IP. DNS can take a few
  minutes. Verify with `dig +short life.yourdomain.com` from your laptop.

## 1. SSH in

```bash
ssh root@YOUR_VPS_IP
```

## 2. Find your Traefik network and cert resolver name

Hostinger's template configures Traefik with specific defaults. Confirm them:

```bash
docker ps                              # find the Traefik container name
docker network ls                      # find the network Traefik is on
docker inspect traefik 2>/dev/null \
  | grep -E 'NetworkMode|certresolvers|entryPoints' -A1
```

Typical values are:
- Network: `traefik` (or `proxy`, or `web`)
- Cert resolver: `letsencrypt` (or `myresolver`)

Note both — you'll plug them in below.

## 3. Clone the repo

```bash
cd /opt
git clone https://github.com/jimmyjangas-wq/claude.git life-organizer
cd life-organizer
git checkout claude/life-organization-tracker-DF9c7
```

If the repo is private, use a personal access token:
`git clone https://USERNAME:TOKEN@github.com/jimmyjangas-wq/claude.git life-organizer`

## 4. Generate the Traefik basic-auth string

This protects the app with a username/password prompt.

```bash
docker run --rm httpd:alpine htpasswd -nbB james 'PickAStrongPassword'
```

Output looks like:
```
james:$2y$05$Hkj38d.....
```

You need to **double every `$`** before pasting into `.env`
(Compose treats single `$` as a variable). So `$2y$05$Hkj` becomes
`$$2y$$05$$Hkj`. A quick shell one-liner:

```bash
docker run --rm httpd:alpine htpasswd -nbB james 'PickAStrongPassword' \
  | sed 's/\$/\$\$/g'
```

Copy the output.

## 5. Configure environment

```bash
cp .env.example .env
nano .env
```

Fill in:

```
LIFE_DOMAIN=life.yourdomain.com
LIFE_AUTH=james:$$2y$$05$$...        # from step 4 (doubled $)
TRAEFIK_NETWORK=traefik              # from step 2
CERT_RESOLVER=letsencrypt            # from step 2
```

Save (`Ctrl+O`, Enter, `Ctrl+X`).

## 6. Build and launch

```bash
docker compose up -d --build
docker compose logs -f
```

Wait until you see Streamlit say `You can now view your Streamlit app`. Then
`Ctrl+C` out of logs (the container keeps running).

## 7. Open it on your phone

Visit `https://life.yourdomain.com`. Browser prompts for username + password.

Add to home screen:
- **iPhone (Safari):** Share → "Add to Home Screen"
- **Android (Chrome):** ⋮ menu → "Add to Home screen"

It now opens like a native app, fullscreen.

---

## Updating later

```bash
cd /opt/life-organizer
git pull
docker compose up -d --build
```

## Where your data lives

In a Docker named volume `life-organizer_life-data` (a SQLite file inside it).
Survives container rebuilds and reboots. Back up:

```bash
docker run --rm -v life-organizer_life-data:/data -v "$PWD":/backup alpine \
    tar czf /backup/life-$(date +%F).tar.gz -C /data .
```

Restore the other way. Keep these backups off the server (scp them home).

## Troubleshooting

- **404 from Traefik:** the router rule isn't matching. Double-check
  `LIFE_DOMAIN` in `.env` and that DNS resolves to the VPS.
  `docker compose logs life-organizer` should show Streamlit running.
- **SSL cert pending:** first request can take 30–60s while Let's Encrypt
  issues. Check `docker logs traefik` for ACME errors.
- **Connection refused / Bad Gateway:** the container isn't on Traefik's
  network. `docker network connect <traefik-network> life-organizer` then
  fix `TRAEFIK_NETWORK` in `.env`.
- **Password prompt loops:** the `LIFE_AUTH` value is malformed — make sure
  every `$` is doubled.
