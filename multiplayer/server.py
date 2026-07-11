#!/usr/bin/env python3
"""
SevenBox multiplayer server v4
- Public/private rooms with titles
- Live lobby list for public servers
- Edit/view roles, presence, song sync
- Online-tuned: throttled cursors, light heartbeats, LWW song state
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import logging
import mimetypes
import os
import random
import sys
import time
import zlib
from pathlib import Path
from typing import Any

from websockets.asyncio.server import ServerConnection, serve
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosed, InvalidMessage
from websockets.http11 import Request, Response


def _quiet_websockets_noise() -> None:
    """
    Render/health scanners/bots often open the port without a full HTTP request.
    websockets logs that as InvalidMessage — harmless, but noisy in logs.
    """
    class _DropNoise(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
            try:
                msg = record.getMessage()
            except Exception:
                return True
            junk = (
                "did not receive a valid HTTP request",
                "opening handshake failed",
                "connection closed while reading HTTP request",
                "InvalidMessage",
            )
            return not any(j in msg for j in junk)

    for name in ("websockets", "websockets.server", "websockets.asyncio.server"):
        log = logging.getLogger(name)
        log.addFilter(_DropNoise())
        # keep real errors; filter handles the spam lines
        if log.level == logging.NOTSET:
            log.setLevel(logging.INFO)


_quiet_websockets_noise()

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT

CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LEN = 5
SEVEN_KEY = "309761!"
MAX_SONG_CHARS = 1_500_000  # ~1.5MB base64 song cap
ALLOWED_THEMES = {
    "default",
    "purple_gold",
    "midnight",
    "matrix",
    "crimson",
    "ocean",
    "sunset",
    "ice",
}
# Site-wide look (everyone sees this) — only seven can change
SITE: dict[str, Any] = {
    "theme": "default",
    "announce": "",
    "announce_ts": 0,
}
# Golden banner is temporary (ms). After this, new joins won't see it either.
ANNOUNCE_TTL_MS = 12_000
BLOCKED_NAMES = {
    "admin", "administrator", "host", "owner", "root", "mod", "moderator",
    "sysadmin", "system", "staff", "op", "operator", "superuser", "sudo",
    "god", "king", "queen", "boss", "leader", "master", "creator",
    "grok", "xai", "beepbox", "server",
}


def normalize_name(n: str) -> str:
    return " ".join(str(n or "").strip().split())[:24]


RANDOM_TITLES = (
    "late night jam",
    "chip soup",
    "beep zone",
    "pixel loft",
    "8-bit attic",
    "synth kitchen",
    "noise closet",
    "loop station",
    "midnight grid",
    "cassette club",
    "pulse room",
    "hex jam",
    "square wave cafe",
    "arcade after dark",
    "tiny stadium",
    "floppy disk party",
    "retro rocket",
    "glitch garden",
    "coin sound lab",
    "bass bunker",
)


def random_room_title() -> str:
    return random.choice(RANDOM_TITLES)


def normalize_title(t: str) -> str:
    t = " ".join(str(t or "").strip().split())[:40]
    return t or random_room_title()


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
    for bit in ("administrator", "moderator", "sysadmin", "superuser", "sysop"):
        if bit in compact:
            return False, "That name sounds like staff/power. Pick another."
    return True, n


def normalize_code(raw: Any) -> str:
    return str(raw or "").strip().upper().replace(" ", "")


def song_sig(song: str) -> int:
    if not song:
        return 0
    return zlib.crc32(song.encode("utf-8", errors="ignore")) & 0xFFFFFFFF


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
        self.song_ts: int = 0
        self.names: dict[ServerConnection, str] = {}
        self.roles: dict[ServerConnection, str] = {}
        self.presence: dict[ServerConnection, dict[str, Any]] = {}
        self.default_role = "edit"
        self.title = title
        self.public = public
        self.created = time.time()
        self.last_transport: dict[str, Any] = {
            "playing": False,
            "bar": 0,
            "playhead": 0.0,
        }
        self._presence_dirty = False
        self._presence_flush_task: asyncio.Task | None = None
        self._hb_tick = 0
        self._chat_last: dict[ServerConnection, float] = {}
        self.chat_log: list[dict[str, Any]] = []  # last messages for late joiners

    def peer_list(self) -> list[dict[str, Any]]:
        out = []
        for c in self.clients:
            p = self.presence.get(c) or {}
            x = p.get("x")
            y = p.get("y")
            # if we have coords, treat as inside unless explicitly false
            if "inside" in p:
                inside = bool(p.get("inside"))
            else:
                inside = x is not None and y is not None
            try:
                ch = int(p.get("channel", 0) or 0)
            except (TypeError, ValueError):
                ch = 0
            if ch < 0:
                ch = 0
            try:
                bar = int(p.get("bar", 0) or 0)
            except (TypeError, ValueError):
                bar = 0
            nm = self.names.get(c, "player")
            out.append(
                {
                    "name": nm,
                    "role": self.roles.get(c, "edit"),
                    "channel": ch,
                    "bar": bar,
                    "x": x,
                    "y": y,
                    "inside": inside,
                    "isHost": c is self.host,
                    # Only real "seven" (key-checked at join) can ever be true
                    "isOwner": is_seven_name(nm),
                }
            )
        return out

    def lobby_entry(self) -> dict[str, Any]:
        host_name = self.names.get(self.host, "host")
        return {
            "code": self.code,
            "title": self.title,
            "public": self.public,
            "host": host_name,
            "hostIsOwner": is_seven_name(host_name),
            "count": len(self.clients),
            "defaultRole": self.default_role,
            "created": int(self.created),
        }


rooms: dict[str, Room] = {}
client_room: dict[ServerConnection, str] = {}
all_clients: set[ServerConnection] = set()


def active_announce() -> tuple[str, int]:
    """Return (text, ts) only while the banner is still within TTL; else clear."""
    text = str(SITE.get("announce") or "")
    ts = int(SITE.get("announce_ts") or 0)
    if not text or not ts:
        return "", 0
    age = int(time.time() * 1000) - ts
    if age > ANNOUNCE_TTL_MS:
        SITE["announce"] = ""
        SITE["announce_ts"] = 0
        return "", 0
    return text, ts


def presence_stats() -> dict[str, Any]:
    """How many people are connected / in rooms right now."""
    in_rooms = sum(len(r.clients) for r in rooms.values())
    ann, ann_ts = active_announce()
    return {
        "type": "stats",
        "online": len(all_clients),
        "inRooms": in_rooms,
        "rooms": len(rooms),
        "public": len([r for r in rooms.values() if r.public]),
        "lobby": public_lobby(),
        "theme": SITE["theme"],
        "announce": ann,
        "announceTs": ann_ts,
    }


def is_seven_admin(msg: dict[str, Any]) -> bool:
    """Owner commands require name seven + the special key (server-side)."""
    name = normalize_name(str(msg.get("name") or ""))
    key = str(msg.get("nameKey") or "")
    return is_seven_name(name) and key == SEVEN_KEY


def all_rooms_admin() -> list[dict[str, Any]]:
    out = []
    for r in rooms.values():
        out.append(
            {
                "code": r.code,
                "title": r.title,
                "public": r.public,
                "host": r.names.get(r.host, "host"),
                "count": len(r.clients),
                "defaultRole": r.default_role,
                "peers": r.peer_list(),
            }
        )
    out.sort(key=lambda e: (-e["count"], e["code"]))
    return out


async def force_leave_client(ws: ServerConnection, reason: str = "removed") -> None:
    await leave(ws)  # already broadcasts lobby when needed
    await send(ws, {"type": "kicked", "reason": reason})
    await send(ws, {"type": "left"})


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


async def flush_presence(room: Room) -> None:
    """~8 Hz max presence broadcast — channel marks only (lighter on free hosts)."""
    try:
        await asyncio.sleep(0.12)
        if room.code not in rooms or rooms.get(room.code) is not room:
            return
        if not room._presence_dirty:
            return
        room._presence_dirty = False
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
    except Exception:
        pass
    finally:
        room._presence_flush_task = None
        if room._presence_dirty and room.code in rooms and rooms.get(room.code) is room:
            room._presence_flush_task = asyncio.create_task(flush_presence(room))


def schedule_presence_broadcast(room: Room) -> None:
    room._presence_dirty = True
    if room._presence_flush_task is None or room._presence_flush_task.done():
        room._presence_flush_task = asyncio.create_task(flush_presence(room))


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
    await broadcast_stats()


async def broadcast_stats() -> None:
    payload = presence_stats()
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

    promoted = None
    if room.host is ws:
        room.host = next(iter(room.clients))
        room.roles[room.host] = "host"
        promoted = room.host

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
    # New host must unlock host controls immediately (not stay stuck as edit)
    if promoted is not None:
        await send(
            promoted,
            {
                "type": "your_role",
                "role": "host",
                "defaultRole": room.default_role,
                "peers": room.peer_list(),
                "host": room.names.get(room.host, "host"),
            },
        )
    await broadcast_lobby()


async def ws_handler(ws: ServerConnection) -> None:
    all_clients.add(ws)
    stats = presence_stats()
    ann, ann_ts = active_announce()
    try:
        await send(
            ws,
            {
                "type": "hello",
                "app": "SevenBox",
                "v": 6,
                "online": stats["online"],
                "inRooms": stats["inRooms"],
                "rooms": stats["rooms"],
                "public": stats["public"],
                "theme": SITE["theme"],
                "announce": ann,
                "announceTs": ann_ts,
            },
        )
        await send(ws, {"type": "lobby", "servers": public_lobby()})
        await send(
            ws,
            {
                "type": "site_theme",
                "theme": SITE["theme"],
                "announce": ann,
                "announceTs": ann_ts,
            },
        )
        await broadcast_stats()
    except (ConnectionClosed, InvalidMessage, OSError):
        all_clients.discard(ws)
        return
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
                await send(ws, presence_stats())

            elif mtype == "stats":
                await send(ws, presence_stats())

            elif mtype == "create":
                await leave(ws)
                ok, name_or_err = validate_player_name(
                    str(msg.get("name") or ""), msg.get("nameKey")
                )
                if not ok:
                    await send(ws, {"type": "error", "message": name_or_err})
                    continue
                name = name_or_err
                # blank title → random fun name (not just "Untitled")
                raw_title = " ".join(str(msg.get("title") or "").strip().split())
                title = normalize_title(raw_title) if raw_title else random_room_title()
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
                try:
                    ch0 = int(msg.get("channel") if msg.get("channel") is not None else 0)
                except (TypeError, ValueError):
                    ch0 = 0
                try:
                    bar0 = int(msg.get("bar") if msg.get("bar") is not None else 0)
                except (TypeError, ValueError):
                    bar0 = 0
                if ch0 < 0:
                    ch0 = 0
                if bar0 < 0:
                    bar0 = 0
                room.presence[ws] = {
                    "channel": ch0,
                    "bar": bar0,
                }
                if msg.get("song"):
                    song = str(msg["song"])
                    if len(song) <= MAX_SONG_CHARS:
                        room.song = song
                        room.song_ts = int(msg.get("ts") or time.time() * 1000)
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
                        "ts": room.song_ts,
                        "chat": room.chat_log[-30:],
                        "isOwner": is_seven_name(name),
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
                            "message": (
                                f"Room {code or '?'} not found. "
                                "It may be private, closed, or you're on a different link."
                            ),
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
                try:
                    chj = int(msg.get("channel") if msg.get("channel") is not None else 0)
                except (TypeError, ValueError):
                    chj = 0
                try:
                    barj = int(msg.get("bar") if msg.get("bar") is not None else 0)
                except (TypeError, ValueError):
                    barj = 0
                if chj < 0:
                    chj = 0
                if barj < 0:
                    barj = 0
                room.presence[ws] = {
                    "channel": chj,
                    "bar": barj,
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
                        "ts": room.song_ts,
                        "chat": room.chat_log[-30:],
                        "isOwner": is_seven_name(name),
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
                            "ts": room.song_ts,
                        },
                    )
                    continue
                song = str(msg.get("song") or "")
                if not song or len(song) > MAX_SONG_CHARS:
                    continue
                ts = int(msg.get("ts") or 0)
                # Last-write-wins: drop stale packets (fixes note flicker over lag)
                if ts and room.song_ts and ts < room.song_ts:
                    continue
                if song == room.song and ts and ts <= room.song_ts:
                    continue
                room.song = song
                room.song_ts = ts or int(time.time() * 1000)
                await broadcast_room(
                    room,
                    {
                        "type": "state",
                        "song": song,
                        "from": room.names.get(ws, "player"),
                        "role": role,
                        "ts": room.song_ts,
                        "seq": int(msg.get("seq") or 0),
                        "sig": song_sig(song),
                    },
                    skip=ws,
                )

            elif mtype == "transport":
                code = client_room.get(ws)
                if not code:
                    continue
                room = rooms.get(code)
                if not room:
                    continue
                role = room.roles.get(ws, "view")
                if role == "view":
                    continue
                restart = bool(msg.get("restart") or msg.get("snap"))
                # Never persist restart on last_transport — heartbeats would re-fire it forever
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
                        "restart": restart,
                        "from": room.names.get(ws, "player"),
                        "ts": int(msg.get("ts") or time.time() * 1000),
                    },
                    skip=ws,
                )

            elif mtype == "set_default_role":
                code = client_room.get(ws)
                room = rooms.get(code) if code else None
                if not room or room.host is not ws:
                    await send(
                        ws, {"type": "error", "message": "only host can change permissions"}
                    )
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
                try:
                    ch = int(msg.get("channel") if msg.get("channel") is not None else 0)
                except (TypeError, ValueError):
                    ch = 0
                if ch < 0:
                    ch = 0
                if ch > 64:
                    ch = 64
                try:
                    bar = int(msg.get("bar") if msg.get("bar") is not None else 0)
                except (TypeError, ValueError):
                    bar = 0
                room.presence[ws] = {
                    "channel": ch,
                    "bar": bar,
                    "x": float(msg["x"]) if msg.get("x") is not None else None,
                    "y": float(msg["y"]) if msg.get("y") is not None else None,
                    "inside": bool(msg.get("inside")),
                }
                if msg.get("name"):
                    # only update display name if already in room (don't hijack)
                    if ws in room.names:
                        room.names[ws] = str(msg.get("name"))[:24]
                schedule_presence_broadcast(room)

            elif mtype == "chat":
                code = client_room.get(ws)
                room = rooms.get(code) if code else None
                if not room or ws not in room.clients:
                    await send(ws, {"type": "error", "message": "join a room to chat"})
                    continue
                name = room.names.get(ws, "player")
                text = " ".join(str(msg.get("text") or "").strip().split())
                if not text:
                    continue
                if len(text) > 180:
                    text = text[:180]
                # owner-only: clear room chat
                if text.lower() in ("/clear", "/clearchat") and is_seven_name(name):
                    room.chat_log = []
                    await broadcast_room(
                        room,
                        {
                            "type": "chat_clear",
                            "by": name,
                            "ts": int(time.time() * 1000),
                        },
                    )
                    continue
                # rate limit ~3 msgs / 2s
                now_t = time.time()
                last_t = room._chat_last.get(ws, 0.0)
                if now_t - last_t < 0.35:
                    continue
                room._chat_last[ws] = now_t
                entry = {
                    "type": "chat",
                    "name": name,
                    "text": text,
                    "isOwner": is_seven_name(name),
                    "isHost": ws is room.host,
                    "ts": int(now_t * 1000),
                }
                room.chat_log.append(entry)
                if len(room.chat_log) > 40:
                    room.chat_log = room.chat_log[-40:]
                await broadcast_room(room, entry)

            elif mtype == "request_sync":
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
                        "ts": room.song_ts or int(time.time() * 1000),
                        "sig": song_sig(room.song),
                    },
                )

            elif mtype == "ping":
                await send(ws, {"type": "pong", "t": time.time()})

            elif mtype == "leave":
                await leave(ws)
                await send(ws, {"type": "left"})
                await broadcast_lobby()

            # ── Owner (seven) admin ──────────────────────────────────────
            elif mtype == "admin_list":
                if not is_seven_admin(msg):
                    await send(ws, {"type": "error", "message": "owner only"})
                    continue
                await send(
                    ws,
                    {
                        "type": "admin_list",
                        "rooms": all_rooms_admin(),
                        "online": len(all_clients),
                        "theme": SITE["theme"],
                        "announce": active_announce()[0],
                    },
                )

            elif mtype == "admin_kick":
                if not is_seven_admin(msg):
                    await send(ws, {"type": "error", "message": "owner only"})
                    continue
                target = normalize_name(str(msg.get("target") or ""))
                room_code = normalize_code(msg.get("room") or "")
                if not target:
                    await send(ws, {"type": "error", "message": "pick someone to kick"})
                    continue
                reason = str(msg.get("reason") or "Removed by seven")[:80]
                kicked = 0
                for room in list(rooms.values()):
                    if room_code and room.code != room_code:
                        continue
                    for c in list(room.clients):
                        if normalize_name(room.names.get(c, "")) == target:
                            # never kick yourself by name match in same session unless explicit
                            await force_leave_client(c, reason)
                            kicked += 1
                if kicked:
                    await send(
                        ws,
                        {
                            "type": "admin_ok",
                            "action": "kick",
                            "target": target,
                            "kicked": kicked,
                            "message": f"Kicked {target} ({kicked})",
                        },
                    )
                    await broadcast_stats()
                else:
                    await send(ws, {"type": "error", "message": f"No player named {target}"})

            elif mtype == "admin_close_room":
                if not is_seven_admin(msg):
                    await send(ws, {"type": "error", "message": "owner only"})
                    continue
                code = normalize_code(msg.get("room") or "")
                room = rooms.get(code)
                if not room:
                    await send(ws, {"type": "error", "message": "room not found"})
                    continue
                reason = str(msg.get("reason") or "Room closed by seven")[:80]
                for c in list(room.clients):
                    await force_leave_client(c, reason)
                await send(
                    ws,
                    {
                        "type": "admin_ok",
                        "action": "close_room",
                        "room": code,
                        "message": f"Closed room {code}",
                    },
                )
                await broadcast_stats()

            elif mtype == "admin_set_theme":
                if not is_seven_admin(msg):
                    await send(ws, {"type": "error", "message": "owner only"})
                    continue
                theme = str(msg.get("theme") or "default").strip().lower().replace("-", "_")
                if theme not in ALLOWED_THEMES:
                    await send(
                        ws,
                        {
                            "type": "error",
                            "message": "bad theme — " + ", ".join(sorted(ALLOWED_THEMES)),
                        },
                    )
                    continue
                SITE["theme"] = theme
                ann, ann_ts = active_announce()
                payload = {
                    "type": "site_theme",
                    "theme": SITE["theme"],
                    "announce": ann,
                    "announceTs": ann_ts,
                    "from": "seven",
                }
                raw = json.dumps(payload, separators=(",", ":"))
                for c in list(all_clients):
                    try:
                        await c.send(raw)
                    except Exception:
                        pass
                await send(
                    ws,
                    {
                        "type": "admin_ok",
                        "action": "theme",
                        "theme": SITE["theme"],
                        "message": f"Theme → {SITE['theme']} (everyone)",
                    },
                )

            elif mtype == "admin_announce":
                if not is_seven_admin(msg):
                    await send(ws, {"type": "error", "message": "owner only"})
                    continue
                text = " ".join(str(msg.get("text") or "").strip().split())[:160]
                SITE["announce"] = text
                SITE["announce_ts"] = int(time.time() * 1000) if text else 0
                payload = {
                    "type": "announce",
                    "text": text,
                    "ts": SITE["announce_ts"],
                    "ttlMs": ANNOUNCE_TTL_MS if text else 0,
                    "from": "seven",
                }
                raw = json.dumps(payload, separators=(",", ":"))
                for c in list(all_clients):
                    try:
                        await c.send(raw)
                    except Exception:
                        pass
                await send(
                    ws,
                    {
                        "type": "admin_ok",
                        "action": "announce",
                        "message": (
                            f"Announcement sent ({ANNOUNCE_TTL_MS // 1000}s)"
                            if text
                            else "Announcement cleared"
                        ),
                    },
                )
                # auto-clear stored banner so it doesn't stick forever
                if text:
                    async def _expire_announce(expected_ts: int) -> None:
                        await asyncio.sleep(ANNOUNCE_TTL_MS / 1000.0)
                        if SITE.get("announce_ts") == expected_ts:
                            SITE["announce"] = ""
                            SITE["announce_ts"] = 0

                    asyncio.create_task(_expire_announce(SITE["announce_ts"]))

            elif mtype == "admin_set_role":
                # Force someone's role in a room (edit/view)
                if not is_seven_admin(msg):
                    await send(ws, {"type": "error", "message": "owner only"})
                    continue
                code = normalize_code(msg.get("room") or "")
                target = normalize_name(str(msg.get("target") or ""))
                role = str(msg.get("role") or "view").lower()
                if role not in ("edit", "view"):
                    await send(ws, {"type": "error", "message": "role must be edit or view"})
                    continue
                room = rooms.get(code)
                if not room or not target:
                    await send(ws, {"type": "error", "message": "room/target required"})
                    continue
                found = None
                for c in room.clients:
                    if normalize_name(room.names.get(c, "")) == target:
                        found = c
                        break
                if not found:
                    await send(ws, {"type": "error", "message": "player not in that room"})
                    continue
                if found is room.host:
                    await send(ws, {"type": "error", "message": "can't demote room host this way"})
                    continue
                room.roles[found] = role
                await send(found, {"type": "your_role", "role": role, "defaultRole": room.default_role})
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
                await send(
                    ws,
                    {
                        "type": "admin_ok",
                        "action": "set_role",
                        "message": f"{target} → {role} in {code}",
                    },
                )

            else:
                await send(ws, {"type": "error", "message": "unknown type"})
    except (ConnectionClosed, InvalidMessage, OSError):
        # client navigated away / flaky network — normal
        pass
    except Exception as e:
        # don't crash the whole process for one bad client
        print(f"ws_handler client error: {type(e).__name__}: {e}", file=sys.stderr)
    finally:
        all_clients.discard(ws)
        try:
            await leave(ws)
        except Exception:
            pass


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
    method = ""
    try:
        method = (request.method or "GET").upper()
    except Exception:
        method = "GET"

    # WebSocket upgrade path only
    if path == "/ws" or path.startswith("/ws?"):
        return None

    # Health / probes (Render, bots, uptime checkers)
    if path in ("/health", "/healthz", "/ready", "/ping"):
        st = presence_stats()
        body = json.dumps(
            {
                "ok": True,
                "app": "SevenBox",
                "v": 6,
                "online": st["online"],
                "inRooms": st["inRooms"],
                "rooms": st["rooms"],
                "public": st["public"],
                "theme": SITE["theme"],
                "lobby": public_lobby(),
            }
        ).encode()
        headers = Headers(
            [
                ("Content-Type", "application/json"),
                ("Cache-Control", "no-store"),
                ("Access-Control-Allow-Origin", "*"),
            ]
        )
        if method == "HEAD":
            return Response(200, "OK", headers, b"")
        return Response(200, "OK", headers, body)

    # CORS preflight
    if method == "OPTIONS":
        return Response(
            204,
            "No Content",
            Headers(
                [
                    ("Access-Control-Allow-Origin", "*"),
                    ("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS"),
                    ("Access-Control-Allow-Headers", "*"),
                    ("Access-Control-Max-Age", "86400"),
                ]
            ),
            b"",
        )

    if method not in ("GET", "HEAD"):
        return Response(
            405,
            "Method Not Allowed",
            Headers([("Content-Type", "text/plain"), ("Allow", "GET, HEAD, OPTIONS")]),
            b"Method not allowed",
        )

    file_path = safe_path(path)
    if file_path is None:
        return Response(
            404, "Not Found", Headers([("Content-Type", "text/plain")]), b"Not found"
        )

    data = file_path.read_bytes()
    ctype = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    if file_path.suffix == ".html":
        ctype = "text/html; charset=utf-8"
    elif file_path.suffix == ".js":
        ctype = "application/javascript; charset=utf-8"
    elif file_path.suffix == ".css":
        ctype = "text/css; charset=utf-8"
    elif file_path.suffix == ".wav":
        ctype = "audio/wav"

    accept = ""
    try:
        accept = request.headers.get("Accept-Encoding", "") or ""
    except Exception:
        pass

    # HTML/JS always revalidate so deploy fixes show up; static media can cache briefly
    if file_path.suffix in (".html", ".js"):
        cache = "no-cache, must-revalidate"
    elif file_path.suffix in (".wav", ".png", ".jpg", ".ico", ".svg"):
        cache = "public, max-age=3600"
    else:
        cache = "no-cache"

    header_list = [
        ("Content-Type", ctype),
        ("Cache-Control", cache),
        ("Access-Control-Allow-Origin", "*"),
        ("X-Content-Type-Options", "nosniff"),
    ]
    if method == "HEAD":
        return Response(200, "OK", Headers(header_list), b"")

    if "gzip" in accept.lower() and len(data) > 1500 and file_path.suffix != ".wav":
        data = gzip.compress(data, compresslevel=5)
        header_list.append(("Content-Encoding", "gzip"))
        header_list.append(("Vary", "Accept-Encoding"))
    return Response(200, "OK", Headers(header_list), data)


async def room_heartbeat_loop() -> None:
    """Light keep-alive. Full song only every ~12s (not every tick) to cut lag/glitch."""
    tick = 0
    while True:
        await asyncio.sleep(3.0)
        tick += 1
        if tick % 2 == 0:
            try:
                await broadcast_stats()
            except Exception:
                pass
        now = int(time.time() * 1000)
        for room in list(rooms.values()):
            if not room.clients:
                continue
            room._hb_tick = getattr(room, "_hb_tick", 0) + 1
            payload: dict[str, Any] = {
                "type": "heartbeat",
                "transport": getattr(
                    room,
                    "last_transport",
                    {"playing": False, "bar": 0, "playhead": 0.0},
                ),
                "ts": now,
                "count": len(room.clients),
                "title": room.title,
                "code": room.code,
                "sig": song_sig(room.song),
                "songLen": len(room.song or ""),
            }
            # Full song recovery rarely (~30s) — frequent pushes caused playhead jumps
            if room._hb_tick % 10 == 0 and room.song:
                payload["song"] = room.song
                payload["songTs"] = room.song_ts
            # Never include restart flags in heartbeat transport
            tr = payload.get("transport") or {}
            if isinstance(tr, dict) and tr.get("restart"):
                payload["transport"] = {
                    "playing": bool(tr.get("playing")),
                    "bar": int(tr.get("bar") or 0),
                    "playhead": float(tr.get("playhead") or 0),
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
    # Flush immediately so Render sees "listening" logs during port scan
    def log(msg: str) -> None:
        print(msg, flush=True)

    log("SevenBox multiplayer v6 — owner admin + site themes")
    log(f"  Binding: {host}:{port}")
    log(f"  Open:    http://127.0.0.1:{port}/chipbox.html")
    log(f"  WS:      ws://127.0.0.1:{port}/ws")
    log(f"  Health:  http://127.0.0.1:{port}/health")
    # open_timeout: drop silent/probe connections that never send HTTP
    async with serve(
        ws_handler,
        host,
        port,
        process_request=process_request,
        ping_interval=20,
        ping_timeout=20,
        close_timeout=5,
        open_timeout=10,
        max_size=2 * 1024 * 1024,
        compression=None,  # lower CPU on free tier
    ):
        log(f"  LISTENING on http://{host}:{port} (Render port scan should pass)")
        asyncio.create_task(room_heartbeat_loop())
        await asyncio.get_running_loop().create_future()


def main() -> None:
    p = argparse.ArgumentParser()
    env_port = os.environ.get("PORT", "8765")
    try:
        default_port = int(str(env_port).strip() or "8765")
    except ValueError:
        default_port = 8765
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=default_port)
    args = p.parse_args()
    try:
        asyncio.run(main_async(args.host, args.port))
    except KeyboardInterrupt:
        print("\nbye", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
