# SevenBox

**Private chip-music studio** for [seven](https://github.com/cxt11100) — sketch songs in the browser and jam live with friends.

Free online chiptune song editor with multiplayer rooms and a permanent free host.

---

## Quick links

| | |
|---|---|
| **Play** | [https://sevenbox.onrender.com/chipbox.html](https://sevenbox.onrender.com/chipbox.html) |
| **Discord** | [https://discord.gg/j9HQdatjP](https://discord.gg/j9HQdatjP) |
| **Health** | [https://sevenbox.onrender.com/health](https://sevenbox.onrender.com/health) |
| **Repo** | [github.com/cxt11100/sevenbox](https://github.com/cxt11100/sevenbox) |

---

## Community (Discord)

Hang out, drop room codes, share jams, and find people online:

### → [Join the SevenBox Discord](https://discord.gg/j9HQdatjP)

Use Discord to:
- Post **“hosting now”** + a room code or invite link  
- Ask if anyone wants to jam  
- Share finished songs / exports  
- Get a heads-up when the free host is waking up (first load can be slow)

---

## Play online (friends)

**Everyone always uses the same app link:**

**[https://sevenbox.onrender.com/chipbox.html](https://sevenbox.onrender.com/chipbox.html)**

No install. No same Wi‑Fi. No tunnel. No launcher required for online play.

### How to jam

1. Open the app (or join via [Discord](https://discord.gg/j9HQdatjP))  
2. Enter a **name**  
3. **Host server** (public or private) **or** join from the public list / room code  
4. Place notes together — **song edits** and **play/stop** sync for editors  
5. Optional: **Share invite** to copy a link like  
   `https://sevenbox.onrender.com/chipbox.html?room=ABC12`

### Free host note

Render’s free tier **sleeps** when idle. The first open after a while can take **30–60 seconds**. After that it should feel normal. If it fails to load, wait a minute and refresh — or say so in Discord.

---

## Features

- **Pattern tracker** (notes, channels, drums, patterns)  
- **Multiplayer** rooms: public lobby or private codes  
- **Host / edit / view** roles  
- Live **song sync** + **play/stop**  
- Remote **cursors** (see who’s on the grid)  
- Works on **phone and desktop** browsers  
- Songs you make are **yours** (export as usual; no account required)

### Handy keys (multiplayer)

| Key | What |
|-----|------|
| **Space** | Play / pause (syncs to the room) |
| **F** (host) | Restart from the start for everyone |
| **Ctrl+F** / **Cmd+F** | Restart from start (BeepBox + room sync) |

---

## Run locally (optional)

For solo use or development off the public host:

```bash
# Python 3.10+ recommended
pip install -r requirements.txt
python multiplayer/server.py
```

Open: [http://127.0.0.1:8765/chipbox.html](http://127.0.0.1:8765/chipbox.html)

Helpers (if present):

```bash
./start-sevenbox.sh
# or
python SevenBox-Launcher.py
```

Online multiplayer for friends still uses the **Render URL**, not your PC.

---

## Deploy (permanent free host)

Stack: **GitHub** + **[Render](https://render.com)** free web service.

1. Push this repo to GitHub  
2. Render → **New → Blueprint** (reads `render.yaml`)  
   — or **Web Service**:
   - **Build:** `pip install -r requirements.txt`  
   - **Start:** `python multiplayer/server.py --host 0.0.0.0 --port $PORT`  
   - **Plan:** Free  
3. Open `https://YOUR-APP.onrender.com/chipbox.html`

More detail: [HOSTING.md](./HOSTING.md).

---

## Project layout

| Path | What |
|------|------|
| `chipbox.html` | App shell + UI |
| `chipbox-app.js` | BeepBox engine + multiplayer client |
| `multiplayer/server.py` | WebSocket server + static files |
| `render.yaml` | Render free-host config |
| `requirements.txt` | Python deps (`websockets`) |
| `silent.wav` | iOS audio keep-alive helper |
| `HOSTING.md` | Deploy notes |
| `README.md` | You are here |

---

## Credits & ownership

- **SevenBox** — free chiptune editor + multiplayer  
- **Community:** [Discord](https://discord.gg/j9HQdatjP)  
- **Owner:** seven  

---

## License

Private SevenBox build unless stated otherwise.

---

## Support / contact

- **Discord:** [https://discord.gg/j9HQdatjP](https://discord.gg/j9HQdatjP)  
- **GitHub:** [cxt11100/sevenbox](https://github.com/cxt11100/sevenbox)  

Open the app, hop in Discord, and host a room. That’s the whole loop.
