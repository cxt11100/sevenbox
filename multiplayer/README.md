# SevenBox multiplayer

Browser multiplayer for SevenBox on a **permanent host** (e.g. Render).

## Friends (normal use)

1. Open the same site forever, e.g. `https://sevenbox.onrender.com/chipbox.html`
2. Enter a name
3. **Host server** (public or private) **or** join from the public list / room code
4. **Share invite** copies a link like  
   `https://sevenbox.onrender.com/chipbox.html?room=ABC12`

No same Wi‑Fi. No tunnel. No launcher required for online play.

**Note:** Free hosts sleep when idle — first open can take 30–60s.

## Local dev (optional)

```bash
pip install -r requirements.txt
python multiplayer/server.py
# http://127.0.0.1:8765/chipbox.html
```

## Health

`GET /health` → `{"ok": true, "app": "SevenBox", "v": 4, ...}`
