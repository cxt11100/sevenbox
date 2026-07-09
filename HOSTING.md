# SevenBox — permanent free host (no same Wi‑Fi)

**Live app (example):** `https://sevenbox.onrender.com/chipbox.html`

When this is live, **everyone always opens the same link**, then:

- **Host** a public/private server (title)
- **Join** from the public list or with a room code

---

## Fast path: Render.com (free)

### A. Put the code on GitHub

On your PC (in the project folder), if not already a git repo:

```bash
cd ~/projects/nyx-agent
git init
git add -A
git commit -m "SevenBox permanent host ready"
```

Then on GitHub.com:

1. Sign in → **New repository**
2. Name it e.g. `sevenbox` (Public is fine)
3. **Don’t** add README (you already have files)
4. Run the commands GitHub shows under “push an existing repository”, like:

```bash
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/sevenbox.git
git push -u origin main
```

### B. Deploy on Render

1. Go to [https://render.com](https://render.com) → sign up (GitHub login is easiest)
2. **New +** → **Blueprint**
3. Connect the `sevenbox` repo
4. Render reads `render.yaml` → create the **sevenbox** web service
5. Wait for deploy (first time a few minutes)
6. Open the service → copy the URL, e.g.

   `https://sevenbox-xxxx.onrender.com`

7. **Your permanent app link:**

   `https://sevenbox-xxxx.onrender.com/chipbox.html`

Bookmark that. Share **that** with friends forever (until you delete the service).

### C. Using it

1. You and friends open **chipbox.html** on that URL  
2. Enter name  
3. **Host server** (Public + title) **or** Join from list / code  
4. No launcher required for online play  

**Note:** Free Render apps **sleep** after ~15 min idle. First open after sleep can take **30–60 seconds**. After that it’s normal.

---

## Optional: keep PC launcher for local-only

Local still works:

```bash
./start-sevenbox.sh
# http://127.0.0.1:8765/chipbox.html
```

Online multiplayer for friends = the **Render URL**, not your PC.

---

## If Blueprint fails — manual Web Service

1. Render → **New** → **Web Service** → connect repo  
2. Settings:
   - **Runtime:** Python  
   - **Build command:** `pip install -r requirements.txt`  
   - **Start command:** `python multiplayer/server.py --host 0.0.0.0 --port $PORT`  
3. Plan: **Free**  
4. Deploy  

---

## Health check

After deploy, open:

`https://YOUR-APP.onrender.com/health`

You should see JSON like `{"ok": true, "app": "SevenBox", ...}`.
