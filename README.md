# SevenBox
**Private chip-music studio** for [seven](https://github.com/cxt11100) — sketch songs in the browser and jam live with friends.

Free online chiptune song editor with multiplayer rooms and a permanent free host.

---

## Quick Links
| | |
|---|---|
| **Play Online** | [https://sevenbox.onrender.com/chipbox.html](https://sevenbox.onrender.com/chipbox.html) |
| **Discord** | [https://discord.gg/j9HQdatjP](https://discord.gg/j9HQdatjP) |
| **Repo** | [github.com/cxt11100/sevenbox](https://github.com/cxt11100/sevenbox) |

---

## How It Works
1. Open the app: [https://sevenbox.onrender.com/chipbox.html](https://sevenbox.onrender.com/chipbox.html)
2. Enter a name
3. **Host** a room (public or private) **or** join an existing room using a room code or invite link
4. Place notes, edit patterns, and control playback together in real time
5. Song edits, play/stop, and restart commands sync instantly for everyone in the room
6. See remote cursors showing who is editing where

**Key shortcuts (in multiplayer):**
- **Space** — Play / Pause (synced to the whole room)
- **F** (host only) — Restart song from the beginning for everyone
- **Ctrl+F** / **Cmd+F** — Restart from start (BeepBox style + room sync)

Songs you create are yours. Export them anytime. No account or login required. Works on both desktop and mobile browsers.

---

## Multiplayer Setup
Everyone always uses the **same link**:  
**[https://sevenbox.onrender.com/chipbox.html](https://sevenbox.onrender.com/chipbox.html)**

- Host a room and share the invite link (example: `https://sevenbox.onrender.com/chipbox.html?room=ABC12`)
- Or join from the public lobby list
- Public rooms are visible to everyone. Private rooms use codes.

**Free host note**: The Render free tier sleeps when idle. First load can take 30–60 seconds. Refresh and wait if needed.

For questions, room codes, finding people to jam with, or help — join the Discord:  
**[Join SevenBox Discord](https://discord.gg/j9HQdatjP)**

---

## Run Locally
You can run SevenBox completely offline for solo use or development.

### Requirements
- Python 3.10 or higher
- Git (to clone the repo)

### Steps

1. Clone the repository:
   ```bash
   git clone https://github.com/cxt11100/sevenbox.git
   cd sevenbox

Install dependencies:Bashpip install -r requirements.txt
Start the local server:Bashpython multiplayer/server.py
Open the app in your browser:
http://127.0.0.1:8765/chipbox.html

Easier Launch (if available)
Run one of these if present in the folder:
Bash./start-sevenbox.sh
# or
python SevenBox-Launcher.py
Local Multiplayer (LAN only)

You use: http://127.0.0.1:8765/chipbox.html
Friends on the same Wi-Fi use: http://YOUR-PC-IP:8765/chipbox.html
(Find your local IP with ipconfig (Windows) or ip addr / ifconfig (Linux/Mac))

Note: Local multiplayer only works on the same network. For playing with friends over the internet, use the public online host.

Project Layout





































PathDescriptionchipbox.htmlMain app shell + UIchipbox-app.jsBeepBox engine + multiplayer clientmultiplayer/server.pyWebSocket server + static file servingrender.yamlRender.com free hosting configrequirements.txtPython dependencies (websockets)silent.waviOS audio unlock helperHOSTING.mdDetailed deployment guide

Deploy Your Own Free Host (Optional)
See HOSTING.md for full instructions on deploying a permanent free instance on Render.

Community & Support
All further questions, help, hosting issues, jams, and sharing go through the Discord:
https://discord.gg/j9HQdatjP
Post “hosting now” + your room code when you open a room.
Enjoy making chiptune!
