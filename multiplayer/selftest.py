#!/usr/bin/env python3
"""Automated SevenBox multiplayer self-test (no browser needed)."""

from __future__ import annotations

import asyncio
import json
import sys
import time
import urllib.request

from websockets.asyncio.client import connect

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
WS = BASE.replace("https://", "wss://").replace("http://", "ws://").rstrip("/") + "/ws"

passed = 0
failed = 0


def ok(name: str) -> None:
    global passed
    passed += 1
    print(f"  PASS  {name}")


def bad(name: str, detail: str = "") -> None:
    global failed
    failed += 1
    print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


async def recv_until(ws, types, timeout=3.0):
    if isinstance(types, str):
        types = {types}
    else:
        types = set(types)
    end = time.time() + timeout
    while time.time() < end:
        raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, end - time.time()))
        msg = json.loads(raw)
        if msg.get("type") in types:
            return msg
    raise TimeoutError(f"no message in {types}")


async def drain_hello(ws):
    # hello + lobby
    await recv_until(ws, {"hello", "lobby"}, timeout=2)
    try:
        await asyncio.wait_for(ws.recv(), timeout=0.3)
    except Exception:
        pass


async def main() -> int:
    print(f"SevenBox self-test → {BASE}")
    print(f"WebSocket        → {WS}")
    print()

    # HTTP health
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=3) as r:
            health = json.loads(r.read().decode())
        if health.get("ok"):
            ok("health endpoint")
        else:
            bad("health endpoint", str(health))
    except Exception as e:
        bad("health endpoint", str(e))
        print("\nServer not reachable. Start: ./start-sevenbox.sh")
        return 1

    # HTML + app js
    for path in ("/chipbox.html", "/chipbox-app.js"):
        try:
            with urllib.request.urlopen(BASE + path, timeout=5) as r:
                data = r.read()
            if len(data) > 1000:
                ok(f"serves {path} ({len(data)} bytes)")
            else:
                bad(f"serves {path}", f"too small: {len(data)}")
        except Exception as e:
            bad(f"serves {path}", str(e))

    print()
    print("WebSocket protocol:")

    try:
        async with connect(WS, open_timeout=5) as a:
            await drain_hello(a)

            # name block
            await a.send(json.dumps({"type": "create", "name": "admin", "title": "X", "public": True}))
            msg = await recv_until(a, {"error", "created"})
            if msg.get("type") == "error":
                ok("blocks power name 'admin'")
            else:
                bad("blocks power name 'admin'", "allowed create")

            # seven without key
            await a.send(json.dumps({"type": "create", "name": "seven", "title": "X", "public": True}))
            msg = await recv_until(a, {"error", "created"})
            if msg.get("type") == "error":
                ok("blocks 'seven' without key")
            else:
                bad("blocks 'seven' without key")

            # seven with key
            await a.send(
                json.dumps(
                    {
                        "type": "create",
                        "name": "seven",
                        "nameKey": "309761!",
                        "title": "Seven Host",
                        "public": True,
                        "song": "SONG_A",
                        "defaultRole": "edit",
                    }
                )
            )
            created = await recv_until(a, {"created", "error", "lobby"})
            while created.get("type") != "created":
                if created.get("type") == "error":
                    bad("seven with key can host", created.get("message", ""))
                    created = None
                    break
                created = await recv_until(a, {"created", "error", "lobby"})
            if created and created.get("type") == "created":
                ok("seven with key can host")
                code = created["room"]
                title = created.get("title")
            else:
                # fallback host
                await a.send(
                    json.dumps(
                        {
                            "type": "create",
                            "name": "Tester482",
                            "title": "AutoTest Public",
                            "public": True,
                            "song": "SONG_A",
                            "defaultRole": "edit",
                        }
                    )
                )
                created = await recv_until(a, "created")
                code = created["room"]
                title = created.get("title")
                ok("fallback host create")

            async with connect(WS, open_timeout=5) as b:
                await drain_hello(b)
                # lobby should list public
                await b.send(json.dumps({"type": "lobby"}))
                lob = await recv_until(b, "lobby")
                titles = [s.get("title") for s in lob.get("servers", [])]
                if any(t == title for t in titles) or any(s.get("code") == code for s in lob.get("servers", [])):
                    ok("public server appears in lobby")
                else:
                    bad("public server appears in lobby", str(titles))

                # join
                await b.send(json.dumps({"type": "join", "name": "Buddy904", "room": code}))
                joined = await recv_until(b, {"joined", "error"})
                if joined.get("type") == "joined" and joined.get("song") == "SONG_A":
                    ok("join receives song snapshot")
                elif joined.get("type") == "joined":
                    ok("join works")
                    if joined.get("song") != "SONG_A":
                        bad("join song snapshot", f"got {joined.get('song')!r}")
                else:
                    bad("join room", joined.get("message", str(joined)))

                # live state with ts
                ts = int(time.time() * 1000)
                await a.send(json.dumps({"type": "state", "song": "SONG_B", "ts": ts, "seq": 2}))
                got = None
                for _ in range(10):
                    m = await recv_until(b, {"state", "peers", "presence", "lobby", "transport"}, timeout=2)
                    if m.get("type") == "state" and m.get("song") == "SONG_B":
                        got = m
                        break
                if got:
                    ok("live state sync A→B")
                    if got.get("ts"):
                        ok("state carries timestamp")
                    else:
                        bad("state carries timestamp")
                else:
                    bad("live state sync A→B")

                # transport play
                await a.send(json.dumps({"type": "transport", "playing": True, "bar": 2, "playhead": 2.0}))
                tmsg = None
                for _ in range(8):
                    m = await recv_until(b, {"transport", "state", "peers", "presence"}, timeout=2)
                    if m.get("type") == "transport" and m.get("playing") is True:
                        tmsg = m
                        break
                if tmsg:
                    ok("transport play sync")
                else:
                    bad("transport play sync")

                await a.send(json.dumps({"type": "transport", "playing": False, "bar": 2, "playhead": 2.0}))
                tmsg = None
                for _ in range(8):
                    m = await recv_until(b, {"transport", "state", "peers", "presence"}, timeout=2)
                    if m.get("type") == "transport" and m.get("playing") is False:
                        tmsg = m
                        break
                if tmsg:
                    ok("transport stop sync")
                else:
                    bad("transport stop sync")

            # private not in lobby
            async with connect(WS, open_timeout=5) as c:
                await drain_hello(c)
                await c.send(
                    json.dumps(
                        {
                            "type": "create",
                            "name": "PrivHost101",
                            "title": "Secret Hideout",
                            "public": False,
                            "song": "PRIV",
                        }
                    )
                )
                priv = await recv_until(c, "created")
                pcode = priv["room"]
                async with connect(WS, open_timeout=5) as d:
                    await drain_hello(d)
                    await d.send(json.dumps({"type": "lobby"}))
                    lob = await recv_until(d, "lobby")
                    if not any(s.get("title") == "Secret Hideout" for s in lob.get("servers", [])):
                        ok("private server hidden from lobby")
                    else:
                        bad("private server hidden from lobby")
                    await d.send(json.dumps({"type": "join", "name": "Sneak777", "room": pcode}))
                    j = await recv_until(d, {"joined", "error"})
                    if j.get("type") == "joined":
                        ok("private join via code")
                    else:
                        bad("private join via code", j.get("message", ""))

            # view-only cannot push
            async with connect(WS, open_timeout=5) as h:
                await drain_hello(h)
                await h.send(
                    json.dumps(
                        {
                            "type": "create",
                            "name": "ViewHost202",
                            "title": "Watch Only",
                            "public": True,
                            "song": "V0",
                            "defaultRole": "view",
                        }
                    )
                )
                cr = await recv_until(h, "created")
                async with connect(WS, open_timeout=5) as v:
                    await drain_hello(v)
                    await v.send(json.dumps({"type": "join", "name": "Viewer303", "room": cr["room"]}))
                    j = await recv_until(v, "joined")
                    if j.get("role") == "view":
                        ok("joiner gets view role")
                    else:
                        bad("joiner gets view role", str(j.get("role")))
                    await v.send(json.dumps({"type": "state", "song": "HACK", "ts": int(time.time() * 1000)}))
                    m = await recv_until(v, {"state", "error"}, timeout=2)
                    if m.get("type") == "state" and (m.get("readonly") or m.get("song") == "V0"):
                        ok("view-only cannot overwrite song")
                    else:
                        bad("view-only cannot overwrite song", str(m))

    except Exception as e:
        bad("websocket suite", repr(e))

    print()
    print(f"Results: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130)
