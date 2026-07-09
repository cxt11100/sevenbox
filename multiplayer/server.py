#!/usr/bin/env python3
"""
SevenBox multiplayer server v3
- Public/private rooms with titles
- Live lobby list for public servers
- Edit/view roles, presence, song sync
"""

from __future__ import annotations

import argparse
import os
import asyncio
import gzip
import json
import mimetypes
import random
import string
import sys
import time
from pathlib import Path
from typing import Any

from websockets.asyncio.server import ServerConnection, serve
from websockets.datastructures import Headers
from websockets.http11 import Request, Response

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT

CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LEN = 5
SEVEN_KEY = "309761!"
BLOCKED_NAMES = {
    "admin", "administrator", "host", "owner", "root", "mod", "moderator",
    "sysadmin", "system", "staff", "op", "operator", "superuser", "sudo",
    "god", "king", "queen", "boss", "leader", "master", "creator",
    "grok", "xai", "beepbox", "server",
}


def normalize_name(n: str) -> str:
    return " ".join(str(n or "").strip().split())[:24]


def normalize_title(t: str) -> str:
    t = " ".join(str(t or "").strip().split())[:40]
    return t or "Untitled jam"


def is_seven_name(n: str) -> bool:
    s = normalize_name(n).lower()
    compact = "".join(ch for ch in s if ch.isalnum())
    return s == "seven" or compact == "seven"


def validate_player_name(n: str, key: str | None = None) -> tuple[bool, str]:
    n = normalize_name(n)
    if len(n) < 2:
        return False, "Name too short."
    if is_seven_name(n):
        if str(key or "") == SEVEN_KEY:
            return True, n
        return False, 'Name "seven" needs the special key.'
    low = n.lower()
    compact = "".join(ch for ch in low if ch.isalnum())
    if low in BLOCKED_NAMES or compact in BLOCKED_NAMES:
        return False, "That name sounds like staff/power. Pick another."
    # Longer power phrases as substrings only (avoid blocking "HostGuy" via "host")
    for bit in ("administrator", "moderator", "sysadmin", "superuser", "sysop"):
        if bit in compact:
            return False, "That name sounds like staff/power. Pick another."
    return True, n


def normalize_code(raw: Any) -> str:
    return str(raw or "").strip().upper().replace(" ", "")


class Room:
    def __init__(
        self,
        code: str,
        host: ServerConnection,
        host_name: str,
        title: str,
        public: bool,
    ) -> None:
        self.code = code
        self.host = host
        self.clients: set[ServerConnection] = set()
        self.song: str = ""
        self.names: dict[ServerConnection, str] = {}
        self.roles: dict[ServerConnection, str] = {}
        self.presence: dict[ServerConnection, dict[str, Any]] = {}
        self.default_role = "edit"
        self.title = title
        self.public = public
        self.created = time.time()
        self.last_transport: dict[str, Any] = {"playing": False, "bar": 0, "playhead": 0.0}

    def peer_list(self) -> list[dict[str, Any]]:
        out = []
        for c in self.clients:
            p = self.presence.get(c) or {}
            out.append(
                {
                    "name": self.names.get(c, "player"),
                    "role": self.roles.get(c, "edit"),
                    "channel": p.get("channel", 0),
                    "bar": p.get("bar", 0),
                    "x": p.get("x"),
                    "y": p.get("y"),
                    "inside": p.get("inside", False),
                    "isHost": c is self.host,
                }
            )
        return out

    def lobby_entry(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "title": self.title,
            "public": self.public,
            "host": self.names.get(self.host, "host"),
            "count": len(self.clients),
            "defaultRole": self.default_role,
            "created": int(self.created),
        }


rooms: dict[str, Room] = {}
client_room: dict[ServerConnection, str] = {}
all_clients: set[ServerConnection] = set()


def new_code() -> str:
    for _ in range(80):
        code = "".join(random.choice(CODE_CHARS) for _ in range(CODE_LEN))
        if code not in rooms:
            return code
    raise RuntimeError("could not allocate room code")


def public_lobby() -> list[dict[str, Any]]:
    entries = [r.lobby_entry() for r in rooms.values() if r.public]
    entries.sort(key=lambda e: (-e["count"], -e["created"]))
    return entries


async def send(ws: ServerConnection, payload: dict[str, Any]) -> None:
    try:
        await ws.send(json.dumps(payload, separators=(",", ":")))
    except Exception:
        pass


async def broadcast_room(
    room: Room, payload: dict[str, Any], skip: ServerConnection | None = None
) -> None:
    dead: list[ServerConnection] = []
    raw = json.dumps(payload, separators=(",", ":"))
    for c in list(room.clients):
        if c is skip:
            continue
        try:
            await c.send(raw)
        except Exception:
            dead.append(c)
    for c in dead:
        await leave(c)


async def broadcast_lobby() -> None:
    payload = {"type": "lobby", "servers": public_lobby()}
    raw = json.dumps(payload, separators=(",", ":"))
    dead: list[ServerConnection] = []
    for c in list(all_clients):
        try:
            await c.send(raw)
        except Exception:
            dead.append(c)
    for c in dead:
        all_clients.discard(c)
        await leave(c)


async def leave(ws: ServerConnection) -> None:
    code = client_room.pop(ws, None)
    if not code:
        return
    room = rooms.get(code)
    if not room:
        return
    room.clients.discard(ws)
    room.names.pop(ws, None)
    room.roles.pop(ws, None)
    room.presence.pop(ws, None)

    if not room.clients:
        rooms.pop(code, None)
        await broadcast_lobby()
        return

    if room.host is ws:
        room.host = next(iter(room.clients))
        room.roles[room.host] = "host"

    await broadcast_room(
        room,
        {
            "type": "peers",
            "count": len(room.clients),
            "peers": room.peer_list(),
            "defaultRole": room.default_role,
            "host": room.names.get(room.host, "host"),
            "title": room.title,
            "public": room.public,
        },
    )
    await broadcast_lobby()


async def ws_handler(ws: ServerConnection) -> None:
    all_clients.add(ws)
    await send(ws, {"type": "hello", "app": "SevenBox", "v": 3})
    await send(ws, {"type": "lobby", "servers": public_lobby()})
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except Exception:
                await send(ws, {"type": "error", "message": "bad json"})
                continue
            mtype = msg.get("type")

            if mtype == "lobby" or mtype == "list_rooms":
                await send(ws, {"type": "lobby", "servers": public_lobby()})

            elif mtype == "create":
                await leave(ws)
                ok, name_or_err = validate_player_name(
                    str(msg.get("name") or ""), msg.get("nameKey")
                )
                if not ok:
                    await send(ws, {"type": "error", "message": name_or_err})
                    continue
                name = name_or_err
                title = normalize_title(str(msg.get("title") or f"{name}'s jam"))
                public = bool(msg.get("public", True))
                role_default = str(msg.get("defaultRole") or "edit").lower()
                if role_default not in ("edit", "view"):
                    role_default = "edit"

                code = new_code()
                room = Room(code, ws, name, title, public)
                room.default_role = role_default
                room.clients.add(ws)
                room.names[ws] = name
                room.roles[ws] = "host"
                room.presence[ws] = {
                    "channel": int(msg.get("channel") or 0),
                    "bar": int(msg.get("bar") or 0),
                }
                if msg.get("song"):
                    room.song = str(msg["song"])
                rooms[code] = room
                client_room[ws] = code
                await send(
                    ws,
                    {
                        "type": "created",
                        "room": code,
                        "title": room.title,
                        "public": room.public,
                        "role": "host",
                        "defaultRole": room.default_role,
                        "count": 1,
                        "peers": room.peer_list(),
                        "song": room.song,
                        "transport": room.last_transport,
                    },
                )
                await broadcast_lobby()

            elif mtype == "join":
                code = normalize_code(msg.get("room"))
                room = rooms.get(code)
                if not room:
                    await send(
                        ws,
                        {
                            "type": "error",
                            "message": f"Room {code or '?'} not found. It may be private, closed, or you're on a different link.",
                        },
                    )
                    continue
                ok, name_or_err = validate_player_name(
                    str(msg.get("name") or ""), msg.get("nameKey")
                )
                if not ok:
                    await send(ws, {"type": "error", "message": name_or_err})
                    continue
                await leave(ws)
                name = name_or_err
                existing = set(room.names.values())
                base = name
                n = 2
                while name in existing:
                    name = f"{base}{n}"
                    n += 1
                room.clients.add(ws)
                room.names[ws] = name
                room.roles[ws] = room.default_role
                room.presence[ws] = {
                    "channel": int(msg.get("channel") or 0),
                    "bar": int(msg.get("bar") or 0),
                }
                client_room[ws] = code
                await send(
                    ws,
                    {
                        "type": "joined",
                        "room": code,
                        "title": room.title,
                        "public": room.public,
                        "role": room.roles[ws],
                        "defaultRole": room.default_role,
                        "count": len(room.clients),
                        "peers": room.peer_list(),
                        "song": room.song,
                        "host": room.names.get(room.host, "host"),
                        "you": name,
                        "transport": room.last_transport,
                    },
                )
                await broadcast_room(
                    room,
                    {
                        "type": "peers",
                        "count": len(room.clients),
                        "peers": room.peer_list(),
                        "defaultRole": room.default_role,
                        "host": room.names.get(room.host, "host"),
                        "title": room.title,
                        "public": room.public,
                    },
                    skip=ws,
                )
                await broadcast_lobby()

            elif mtype == "state":
                code = client_room.get(ws)
                if not code:
                    await send(ws, {"type": "error", "message": "not in a room"})
                    continue
                room = rooms.get(code)
                if not room:
                    continue
                role = room.roles.get(ws, "view")
                if role == "view":
                    await send(
                        ws,
                        {
                            "type": "state",
                            "song": room.song,
                            "from": "server",
                            "readonly": True,
                        },
                    )
                    continue
                song = str(msg.get("song") or "")
                if not song:
                    continue
                room.song = song
                await broadcast_room(
                    room,
                    {
                        "type": "state",
                        "song": song,
                        "from": room.names.get(ws, "player"),
                        "role": role,
                        "ts": int(msg.get("ts") or time.time() * 1000),
                        "seq": int(msg.get("seq") or 0),
                    },
                    skip=ws,
                )

            elif mtype == "transport":
                # play/stop/playhead — editors only; not local UI prefs
                code = client_room.get(ws)
                if not code:
                    continue
                room = rooms.get(code)
                if not room:
                    continue
                role = room.roles.get(ws, "view")
                if role == "view":
                    continue
                room.last_transport = {
                    "playing": bool(msg.get("playing")),
                    "bar": int(msg.get("bar") or 0),
                    "playhead": float(msg.get("playhead") or 0),
                }
                await broadcast_room(
                    room,
                    {
                        "type": "transport",
                        "playing": room.last_transport["playing"],
                        "bar": room.last_transport["bar"],
                        "playhead": room.last_transport["playhead"],
                        "from": room.names.get(ws, "player"),
                    },
                    skip=ws,
                )

            elif mtype == "set_default_role":
                code = client_room.get(ws)
                room = rooms.get(code) if code else None
                if not room or room.host is not ws:
                    await send(ws, {"type": "error", "message": "only host can change permissions"})
                    continue
                role = str(msg.get("defaultRole") or "edit").lower()
                if role not in ("edit", "view"):
                    await send(ws, {"type": "error", "message": "role must be edit or view"})
                    continue
                room.default_role = role
                apply_all = bool(msg.get("applyToAll"))
                if apply_all:
                    for c in room.clients:
                        if c is not room.host:
                            room.roles[c] = role
                await broadcast_room(
                    room,
                    {
                        "type": "permissions",
                        "defaultRole": room.default_role,
                        "peers": room.peer_list(),
                        "applyToAll": apply_all,
                        "from": room.names.get(ws, "host"),
                        "title": room.title,
                        "public": room.public,
                    },
                )
                for c in room.clients:
                    if c is room.host:
                        continue
                    await send(
                        c,
                        {
                            "type": "your_role",
                            "role": room.roles.get(c, role),
                            "defaultRole": room.default_role,
                        },
                    )
                await broadcast_lobby()

            elif mtype == "presence":
                code = client_room.get(ws)
                room = rooms.get(code) if code else None
                if not room:
                    continue
                room.presence[ws] = {
                    "channel": int(msg.get("channel") or 0),
                    "bar": int(msg.get("bar") or 0),
                    "x": float(msg["x"]) if msg.get("x") is not None else None,
                    "y": float(msg["y"]) if msg.get("y") is not None else None,
                    "inside": bool(msg.get("inside")),
                }
                if msg.get("name"):
                    room.names[ws] = str(msg.get("name"))[:24]
                await broadcast_room(
                    room,
                    {
                        "type": "presence",
                        "peers": room.peer_list(),
                        "count": len(room.clients),
                        "title": room.title,
                        "public": room.public,
                    },
                )

            elif mtype == "request_sync":
                # Client woke from iOS throttle — push full authority state now
                code = client_room.get(ws)
                room = rooms.get(code) if code else None
                if not room:
                    await send(ws, {"type": "error", "message": "not in a room"})
                    continue
                await send(
                    ws,
                    {
                        "type": "full_sync",
                        "song": room.song,
                        "transport": room.last_transport,
                        "peers": room.peer_list(),
                        "count": len(room.clients),
                        "title": room.title,
                        "public": room.public,
                        "defaultRole": room.default_role,
                        "role": room.roles.get(ws, "view"),
                        "ts": int(time.time() * 1000),
                    },
                )

            elif mtype == "ping":
                await send(ws, {"type": "pong", "t": time.time()})

            elif mtype == "leave":
                await leave(ws)
                await send(ws, {"type": "left"})
                await broadcast_lobby()

            else:
                await send(ws, {"type": "error", "message": "unknown type"})
    finally:
        all_clients.discard(ws)
        await leave(ws)
        await broadcast_lobby()


def safe_path(url_path: str) -> Path | None:
    rel = url_path.split("?", 1)[0]
    if rel in ("", "/"):
        rel = "/chipbox.html"
    if ".." in rel or rel.startswith("/."):
        return None
    if rel.startswith("/.venv") or rel.startswith("/multiplayer") or rel.startswith("/.git"):
        return None
    candidate = (STATIC / rel.lstrip("/")).resolve()
    try:
        candidate.relative_to(STATIC.resolve())
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    if ".venv" in candidate.parts:
        return None
    return candidate


async def process_request(connection: ServerConnection, request: Request) -> Response | None:
    path = request.path or "/"
    if path == "/ws" or path.startswith("/ws?"):
        return None

    if path == "/health":
        body = json.dumps(
            {
                "ok": True,
                "app": "SevenBox",
                "v": 3,
                "rooms": len(rooms),
                "public": len([r for r in rooms.values() if r.public]),
                "lobby": public_lobby(),
            }
        ).encode()
        return Response(200, "OK", Headers([("Content-Type", "application/json")]), body)

    file_path = safe_path(path)
    if file_path is None:
        return Response(404, "Not Found", Headers([("Content-Type", "text/plain")]), b"Not found")

    data = file_path.read_bytes()
    ctype = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    if file_path.suffix == ".html":
        ctype = "text/html; charset=utf-8"
    elif file_path.suffix == ".js":
        ctype = "application/javascript; charset=utf-8"
    elif file_path.suffix == ".css":
        ctype = "text/css; charset=utf-8"

    accept = ""
    try:
        accept = request.headers.get("Accept-Encoding", "") or ""
    except Exception:
        pass
    header_list = [
        ("Content-Type", ctype),
        ("Cache-Control", "no-cache"),
        ("Access-Control-Allow-Origin", "*"),
    ]
    if "gzip" in accept.lower() and len(data) > 1500:
        data = gzip.compress(data, compresslevel=6)
        header_list.append(("Content-Encoding", "gzip"))
        header_list.append(("Vary", "Accept-Encoding"))
    return Response(200, "OK", Headers(header_list), data)



async def room_heartbeat_loop() -> None:
    """Push full room state often so idle iPhones catch up when their JS wakes."""
    while True:
        await asyncio.sleep(1.5)
        now = int(time.time() * 1000)
        for room in list(rooms.values()):
            if not room.clients:
                continue
            payload = {
                "type": "heartbeat",
                "song": room.song,
                "transport": getattr(room, "last_transport", {"playing": False, "bar": 0, "playhead": 0.0}),
                "ts": now,
                "peers": room.peer_list(),
                "count": len(room.clients),
                "title": room.title,
                "code": room.code,
            }
            raw = json.dumps(payload, separators=(",", ":"))
            dead = []
            for c in list(room.clients):
                try:
                    await c.send(raw)
                except Exception:
                    dead.append(c)
            for c in dead:
                await leave(c)


async def main_async(host: str, port: int) -> None:
    print("SevenBox multiplayer v3 — public lobby")
    print(f"  Open: http://127.0.0.1:{port}/chipbox.html")
    async with serve(ws_handler, host, port, process_request=process_request):
        asyncio.create_task(room_heartbeat_loop())
        await asyncio.get_running_loop().create_future()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    args = p.parse_args()
    try:
        asyncio.run(main_async(args.host, args.port))
    except KeyboardInterrupt:
        print("\nbye")
        sys.exit(0)


if __name__ == "__main__":
    main()
