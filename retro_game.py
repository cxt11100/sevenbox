#!/usr/bin/env python3
"""NYX-80 Space Raid — retro invaders clone (tkinter, half-screen)."""

import math
import random
import tkinter as tk

# Logical game resolution (classic portrait arcade)
LW, LH = 240, 320


class Game:
    def __init__(self, root: tk.Tk, canvas_w: int, canvas_h: int, scale: float):
        self.root = root
        self.cw = canvas_w
        self.ch = canvas_h
        self.s = scale  # logical → pixels

        root.title("NYX-80 · SPACE RAID")
        root.configure(bg="#0a0a0f")
        root.resizable(False, False)

        self.canvas = tk.Canvas(
            root, width=canvas_w, height=canvas_h, bg="#020408",
            highlightthickness=0,
        )
        self.canvas.pack(padx=10, pady=10)

        font_size = max(10, int(12 * scale / 2))
        tk.Label(
            root,
            text="← → move   Z / SPACE fire   P pause   ENTER start",
            fg="#5a8a5a", bg="#0a0a0f",
            font=("Courier", font_size),
        ).pack(pady=(0, 8))

        self.keys = set()
        root.bind("<KeyPress>", self.on_down)
        root.bind("<KeyRelease>", self.on_up)
        root.focus_force()

        self.mode = "title"
        self.paused = False
        self.score = 0
        self.hi = 0
        self.lives = 3
        self.wave = 1
        self.player = None
        self.bullets = []
        self.ebullets = []
        self.invaders = []
        self.bunkers = []
        self.particles = []
        self.stars = [
            {
                "x": random.randint(0, LW - 1),
                "y": random.randint(0, LH - 1),
                "s": 2 if random.random() < 0.3 else 1,
            }
            for _ in range(50)
        ]
        self.dir = 1
        self.move_timer = 0
        self.move_every = 28
        self.shoot_cd = 0
        self.invuln = 0
        self.flash = 0
        self.ufo = None
        self.ufo_timer = 0
        self.blink = 0

        self.loop()

    # --- coord helpers ---
    def X(self, x):
        return x * self.s

    def Y(self, y):
        return y * self.s

    def R(self, x, y, w, h, **kw):
        self.canvas.create_rectangle(
            self.X(x), self.Y(y), self.X(x + w), self.Y(y + h),
            outline="", **kw,
        )

    def T(self, x, y, text, fill="#7dff7d", size=8, anchor="nw", center=False):
        px = max(10, int(size * self.s))
        if center:
            self.canvas.create_text(
                self.X(x), self.Y(y), text=text, fill=fill,
                font=("Courier", px, "bold" if size >= 12 else "normal"),
            )
        else:
            self.canvas.create_text(
                self.X(x), self.Y(y), text=text, fill=fill,
                font=("Courier", px, "bold" if size >= 12 else "normal"),
                anchor=anchor,
            )

    def on_down(self, e):
        self.keys.add(e.keysym)
        if e.keysym == "Return" and self.mode in ("title", "gameover"):
            self.start()
        if e.keysym in ("p", "P") and self.mode == "play":
            self.paused = not self.paused

    def on_up(self, e):
        self.keys.discard(e.keysym)

    def start(self):
        self.mode = "play"
        self.paused = False
        self.score = 0
        self.lives = 3
        self.wave = 1
        self.player = {"x": LW / 2 - 7, "y": LH - 28, "w": 14, "h": 8, "speed": 1.6}
        self.particles = []
        self.invuln = 0
        self.flash = 0
        self.shoot_cd = 0
        self.spawn_wave(1)

    def spawn_wave(self, wave):
        self.invaders = []
        self.bullets = []
        self.ebullets = []
        self.dir = 1
        self.move_every = max(8, 28 - wave * 2)
        self.move_timer = 0
        self.ufo = None
        self.ufo_timer = 400 + random.randint(0, 300)

        types = [2, 1, 1, 0, 0]
        colors = ["#7dff7d", "#7dc8ff", "#ffdf7d"]
        points = [10, 20, 30]
        for r in range(5):
            for c in range(8):
                t = types[r]
                self.invaders.append({
                    "x": 20 + c * 22,
                    "y": 40 + r * 16,
                    "w": 12, "h": 8,
                    "type": t,
                    "frame": 0,
                    "color": colors[t],
                    "points": points[t],
                    "alive": True,
                })

        self.bunkers = []
        for bx in (36, 92, 148):
            for by in range(3):
                for bx2 in range(5):
                    if by == 2 and 0 < bx2 < 4:
                        continue
                    self.bunkers.append({
                        "x": bx + bx2 * 4,
                        "y": LH - 56 + by * 4,
                        "w": 4, "h": 4,
                        "hp": 3,
                    })

    def aabb(self, a, b):
        return (
            a["x"] < b["x"] + b["w"]
            and a["x"] + a["w"] > b["x"]
            and a["y"] < b["y"] + b["h"]
            and a["y"] + a["h"] > b["y"]
        )

    def explode(self, x, y, color, n=8):
        for _ in range(n):
            a = random.random() * math.pi * 2
            sp = random.uniform(0.4, 1.8)
            self.particles.append({
                "x": x, "y": y,
                "vx": math.cos(a) * sp,
                "vy": math.sin(a) * sp,
                "life": random.randint(12, 28),
                "color": color,
            })

    def kill_player(self):
        p = self.player
        self.explode(p["x"] + 7, p["y"] + 4, "#7dff7d", 14)
        self.lives -= 1
        self.flash = 8
        if self.lives <= 0:
            self.mode = "gameover"
            self.hi = max(self.hi, self.score)
            return
        self.player = {"x": LW / 2 - 7, "y": LH - 28, "w": 14, "h": 8, "speed": 1.6}
        self.invuln = 90
        self.ebullets = []

    def update(self):
        self.blink += 1
        for s in self.stars:
            s["y"] += 0.15 * s["s"]
            if s["y"] > LH:
                s["y"] = 0
                s["x"] = random.randint(0, LW - 1)

        if self.mode != "play" or self.paused:
            return

        p = self.player
        if "Left" in self.keys:
            p["x"] -= p["speed"]
        if "Right" in self.keys:
            p["x"] += p["speed"]
        p["x"] = max(4, min(LW - p["w"] - 4, p["x"]))

        if self.shoot_cd > 0:
            self.shoot_cd -= 1
        if self.invuln > 0:
            self.invuln -= 1
        if self.flash > 0:
            self.flash -= 1

        want_fire = bool({"space", "z", "Z"} & self.keys)
        if want_fire and self.shoot_cd <= 0 and not any(b.get("from") == "p" for b in self.bullets):
            self.bullets.append({
                "x": p["x"] + p["w"] / 2 - 1, "y": p["y"] - 4,
                "w": 2, "h": 6, "vy": -4, "from": "p",
            })
            self.shoot_cd = 10

        for b in self.bullets:
            b["y"] += b["vy"]
        self.bullets = [b for b in self.bullets if -10 < b["y"] < LH]

        for b in self.ebullets:
            b["y"] += b["vy"]
        self.ebullets = [b for b in self.ebullets if b["y"] < LH]

        alive = [i for i in self.invaders if i["alive"]]
        if not alive:
            self.wave += 1
            self.score += 50 * self.wave
            self.spawn_wave(self.wave)
            self.invuln = 40
            return

        self.move_timer += 1
        pace = max(6, self.move_every - (40 - len(alive)) // 3)
        if self.move_timer >= pace:
            self.move_timer = 0
            hit_edge = any(
                inv["x"] + self.dir * 4 < 4 or inv["x"] + inv["w"] + self.dir * 4 > LW - 4
                for inv in alive
            )
            if hit_edge:
                self.dir *= -1
                for inv in alive:
                    inv["y"] += 8
                    inv["frame"] ^= 1
                    if inv["y"] + inv["h"] >= p["y"]:
                        self.lives = 0
                        self.kill_player()
                        return
            else:
                for inv in alive:
                    inv["x"] += self.dir * 4
                    inv["frame"] ^= 1

        if (
            random.random() < 0.012 + self.wave * 0.002
            and len(self.ebullets) < 3 + self.wave // 2
        ):
            cols = {}
            for inv in alive:
                key = round(inv["x"] / 4)
                if key not in cols or inv["y"] > cols[key]["y"]:
                    cols[key] = inv
            shooters = list(cols.values())
            if shooters:
                s = random.choice(shooters)
                self.ebullets.append({
                    "x": s["x"] + s["w"] / 2 - 1,
                    "y": s["y"] + s["h"],
                    "w": 2, "h": 6,
                    "vy": 1.6 + self.wave * 0.08,
                })

        self.ufo_timer -= 1
        if not self.ufo and self.ufo_timer <= 0:
            left = random.random() < 0.5
            self.ufo = {
                "x": -20 if left else LW + 4,
                "y": 18, "w": 16, "h": 6,
                "vx": 1.1 if left else -1.1,
                "points": random.choice([50, 100, 150, 300]),
            }
            self.ufo_timer = 500 + random.randint(0, 400)
        if self.ufo:
            self.ufo["x"] += self.ufo["vx"]
            if self.ufo["x"] < -30 or self.ufo["x"] > LW + 30:
                self.ufo = None

        for b in self.bullets:
            if b.get("from") != "p":
                continue
            for inv in alive:
                if self.aabb(b, inv):
                    inv["alive"] = False
                    b["y"] = -99
                    self.score += inv["points"]
                    self.explode(inv["x"] + 6, inv["y"] + 4, inv["color"], 6)
                    break
            if self.ufo and self.aabb(b, self.ufo):
                self.score += self.ufo["points"]
                self.explode(self.ufo["x"] + 8, self.ufo["y"] + 3, "#ff7d7d", 12)
                self.ufo = None
                b["y"] = -99
            for bk in self.bunkers:
                if bk["hp"] > 0 and self.aabb(b, bk):
                    bk["hp"] -= 1
                    b["y"] = -99
                    break

        for b in self.ebullets:
            for bk in self.bunkers:
                if bk["hp"] > 0 and self.aabb(b, bk):
                    bk["hp"] -= 1
                    b["y"] = LH + 99
                    break
            if self.invuln <= 0 and self.aabb(b, p):
                b["y"] = LH + 99
                self.kill_player()

        for inv in alive:
            for bk in self.bunkers:
                if bk["hp"] > 0 and self.aabb(inv, bk):
                    bk["hp"] = 0
            if self.invuln <= 0 and self.aabb(inv, p):
                self.kill_player()

        for pt in self.particles:
            pt["x"] += pt["vx"]
            pt["y"] += pt["vy"]
            pt["life"] -= 1
        self.particles = [pt for pt in self.particles if pt["life"] > 0]

    def draw_ship(self, x, y):
        self.R(x + 6, y, 2, 3, fill="#7dff7d")
        self.R(x + 2, y + 3, 10, 3, fill="#7dff7d")
        self.R(x, y + 5, 14, 3, fill="#7dff7d")
        self.R(x + 5, y + 4, 4, 2, fill="#c8ffc8")

    def draw_invader(self, inv):
        x, y, col, f, t = inv["x"], inv["y"], inv["color"], inv["frame"], inv["type"]
        if t == 2:
            self.R(x + 4, y, 4, 2, fill=col)
            self.R(x + 2, y + 2, 8, 2, fill=col)
            self.R(x, y + 4, 12, 2, fill=col)
            if f:
                for ox in (0, 4, 8):
                    self.R(x + ox, y + 6, 2, 2, fill=col)
            else:
                for ox in (2, 6, 10):
                    self.R(x + ox, y + 6, 2, 2, fill=col)
        elif t == 1:
            self.R(x + 2, y, 8, 2, fill=col)
            self.R(x, y + 2, 12, 4, fill=col)
            self.R(x + 2, y + 2, 2, 2, fill="#000")
            self.R(x + 8, y + 2, 2, 2, fill="#000")
            if f:
                self.R(x, y + 6, 2, 2, fill=col)
                self.R(x + 10, y + 6, 2, 2, fill=col)
            else:
                self.R(x + 2, y + 6, 2, 2, fill=col)
                self.R(x + 8, y + 6, 2, 2, fill=col)
        else:
            self.R(x + 2, y, 8, 2, fill=col)
            self.R(x, y + 2, 12, 4, fill=col)
            self.R(x + 2, y + 3, 2, 2, fill="#000")
            self.R(x + 8, y + 3, 2, 2, fill="#000")
            if f:
                self.R(x, y + 6, 2, 2, fill=col)
                self.R(x + 4, y + 6, 4, 2, fill=col)
                self.R(x + 10, y + 6, 2, 2, fill=col)
            else:
                self.R(x + 2, y + 6, 2, 2, fill=col)
                self.R(x + 8, y + 6, 2, 2, fill=col)

    def draw(self):
        c = self.canvas
        c.delete("all")

        for s in self.stars:
            self.R(s["x"], s["y"], s["s"], s["s"], fill="#b4dcff")

        if self.mode == "title":
            self.T(LW / 2, 70, "SPACE RAID", size=14, center=True)
            self.T(LW / 2, 90, "NYX-80 ARCADE", fill="#5a8a5a", size=8, center=True)
            demos = [
                (90, 120, 2, "#7dff7d", "30 PTS"),
                (90, 140, 1, "#7dc8ff", "20 PTS"),
                (90, 160, 0, "#ffdf7d", "10 PTS"),
            ]
            for x, y, t, col, label in demos:
                self.draw_invader({"x": x, "y": y, "type": t, "frame": 0, "color": col})
                self.T(x + 24, y + 1, f"= {label}", fill=col, size=8)
            if (self.blink // 20) % 2 == 0:
                self.T(LW / 2, 220, "PRESS ENTER", fill="#c8f0c8", size=10, center=True)
            self.T(LW / 2, 280, f"HI {self.hi}", fill="#5a8a5a", size=8, center=True)
            self.draw_ship(LW / 2 - 7, LH - 40)
            self._scanlines()
            return

        self.T(6, 4, f"SCORE {self.score:05d}", size=8)
        self.T(90, 4, f"HI {self.hi:05d}", fill="#5a8a5a", size=8)
        self.T(180, 4, f"WAVE {self.wave}", fill="#ffdf7d", size=8)

        for bk in self.bunkers:
            if bk["hp"] <= 0:
                continue
            col = {3: "#3a8a3a", 2: "#2a6a2a", 1: "#1a4a1a"}[bk["hp"]]
            self.R(bk["x"], bk["y"], bk["w"], bk["h"], fill=col)

        for inv in self.invaders:
            if inv["alive"]:
                self.draw_invader(inv)

        if self.ufo:
            u = self.ufo
            self.R(u["x"] + 4, u["y"], 8, 2, fill="#ff7d7d")
            self.R(u["x"] + 2, u["y"] + 2, 12, 2, fill="#ff7d7d")
            self.R(u["x"], u["y"] + 4, 16, 2, fill="#ff7d7d")

        if self.invuln <= 0 or (self.invuln // 4) % 2 == 0:
            self.draw_ship(self.player["x"], self.player["y"])

        for b in self.bullets:
            self.R(b["x"], b["y"], b["w"], b["h"], fill="#c8ffc8")
        for b in self.ebullets:
            self.R(b["x"], b["y"], b["w"], b["h"], fill="#ff9f7d")

        for pt in self.particles:
            self.R(pt["x"], pt["y"], 2, 2, fill=pt["color"])

        for i in range(self.lives):
            self.draw_ship(6 + i * 18, LH - 12)

        if self.flash > 0:
            c.create_rectangle(0, 0, self.cw, self.ch, fill="#ff5050", outline="", stipple="gray50")

        if self.paused:
            c.create_rectangle(0, 0, self.cw, self.ch, fill="#000", outline="", stipple="gray50")
            self.T(LW / 2, LH / 2, "PAUSED", fill="#c8f0c8", size=12, center=True)

        if self.mode == "gameover":
            c.create_rectangle(0, 0, self.cw, self.ch, fill="#000", outline="", stipple="gray50")
            self.T(LW / 2, LH / 2 - 16, "GAME OVER", fill="#ff7d7d", size=14, center=True)
            self.T(LW / 2, LH / 2 + 4, f"SCORE {self.score}", fill="#c8f0c8", size=10, center=True)
            if (self.blink // 20) % 2 == 0:
                self.T(LW / 2, LH / 2 + 24, "ENTER TO RETRY", fill="#7dff7d", size=9, center=True)

        self._scanlines()

    def _scanlines(self):
        for y in range(0, self.ch, 4):
            self.canvas.create_line(0, y, self.cw, y, fill="#000000")

    def loop(self):
        self.update()
        self.draw()
        self.root.after(33, self.loop)


def half_screen_canvas(root: tk.Tk):
    """Size canvas to half the monitor, keep 3:4 portrait game ratio."""
    root.update_idletasks()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()

    # Half the screen width, most of the height (title bar + help chrome)
    max_w = sw // 2
    max_h = sh - 100

    # Fit 240:320 (3:4) inside that box
    scale = min(max_w / LW, max_h / LH)
    # keep pixel-ish scaling (prefer integer-ish but allow float)
    scale = max(2.0, scale)

    cw = int(LW * scale)
    ch = int(LH * scale)

    # If still taller than half-area preference, clamp to half height at least as floor
    # User asked "half of my screen" — use up to half width × available height
    if cw > max_w:
        scale = max_w / LW
        cw = int(LW * scale)
        ch = int(LH * scale)
    if ch > max_h:
        scale = max_h / LH
        cw = int(LW * scale)
        ch = int(LH * scale)

    return cw, ch, scale


def main():
    root = tk.Tk()
    cw, ch, scale = half_screen_canvas(root)

    # Window size ≈ half screen; center it
    win_w = cw + 20
    win_h = ch + 60
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - win_w) // 2
    y = max(0, (sh - win_h) // 2 - 20)
    root.geometry(f"{win_w}x{win_h}+{x}+{y}")

    Game(root, cw, ch, scale)
    root.mainloop()


if __name__ == "__main__":
    main()
