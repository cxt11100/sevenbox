# SevenBox multiplayer

Live room sync for SevenBox. Same song, room code, friends join.

## What you need once

- Python 3 (you already have it)
- Project folder: `nyx-agent` with `.venv` (already set up)

## Start the server

```bash
cd ~/projects/nyx-agent
.venv/bin/python multiplayer/server.py
```

Then open:

**http://127.0.0.1:8765/chipbox.html**

## You (host)

1. Open that link  
2. Type your name  
3. Click **Create room**  
4. Copy the **room code** (e.g. `A3K9Q`)  
5. Send friends: the **link** + the **code**

## Friends

1. Open the **same link** you sent  
2. Type their name  
3. Paste the **code**  
4. Click **Join**  
5. Edit — changes show up for everyone (~0.3s)

## Same Wi‑Fi (LAN)

1. On your machine, find your IP:
   ```bash
   hostname -I | awk '{print $1}'
   ```
2. Friends open: `http://YOUR_IP:8765/chipbox.html`  
3. You create room; they join with the code  

Firewall may ask to allow Python on port **8765** — allow it.

## Internet (friends anywhere)

Your PC must be reachable from outside. Easiest free options:

### Option A — Cloudflare Tunnel (free account)

```bash
# install cloudflared, then:
cloudflared tunnel --url http://127.0.0.1:8765
```

It prints a public `https://….trycloudflare.com` URL.  
Share **that** URL + room code. Keep `server.py` running.

### Option B — ngrok

```bash
ngrok http 8765
```

Share the ngrok HTTPS URL + room code.

## Notes

- **Solo still works** if the server is off (multiplayer bar will say server offline).  
- Sync is full-song snapshots (last edit wins if two people change at once).  
- Songs are yours; server only relays room data in memory (nothing saved to disk by the server).  
- Original tracker: [beepbox.co](https://www.beepbox.co/) (John Nesky, MIT).

## Stop

`Ctrl+C` in the terminal running the server.
