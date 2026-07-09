#!/usr/bin/env python3
"""SevenBox Launcher — few buttons to run studio + public phone link."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PY = ROOT / ".venv" / "bin" / "python"
SERVER = ROOT / "multiplayer" / "server.py"
CLOUDFLARED = ROOT / "tools" / "cloudflared"
PORT = 8765

try:
    import tkinter as tk
    from tkinter import messagebox
except ImportError:
    print("tkinter missing")
    sys.exit(1)


class Launcher:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("SevenBox Launcher")
        self.root.configure(bg="#0c0a16")
        self.root.minsize(420, 380)
        self.root.geometry("480x420")

        self.server_proc: subprocess.Popen | None = None
        self.tunnel_proc: subprocess.Popen | None = None
        self.public_url = ""
        self._stop_log = False

        pad = {"padx": 16, "pady": 6}

        title = tk.Label(
            self.root,
            text="SevenBox",
            fg="#e8dfff",
            bg="#0c0a16",
            font=("Segoe UI", 20, "bold"),
        )
        title.pack(pady=(18, 2))

        sub = tk.Label(
            self.root,
            text="Built by Grok · Owned by seven",
            fg="#9a8fb8",
            bg="#0c0a16",
            font=("Segoe UI", 10),
        )
        sub.pack(pady=(0, 12))

        self.status = tk.Label(
            self.root,
            text="Ready — press Start",
            fg="#6dffa8",
            bg="#1a1528",
            font=("Segoe UI", 11),
            wraplength=420,
            justify="left",
            padx=12,
            pady=10,
        )
        self.status.pack(fill="x", **pad)

        self.link_local = tk.Entry(
            self.root,
            font=("Consolas", 10),
            bg="#141022",
            fg="#7ae7ff",
            insertbackground="#fff",
            relief="flat",
        )
        self.link_local.pack(fill="x", **pad)
        self.link_local.insert(0, f"http://127.0.0.1:{PORT}/chipbox.html")

        self.link_public = tk.Entry(
            self.root,
            font=("Consolas", 10),
            bg="#141022",
            fg="#ffd76d",
            insertbackground="#fff",
            relief="flat",
        )
        self.link_public.pack(fill="x", **pad)
        self.link_public.insert(0, "(public phone link appears after Start)")

        btn_frame = tk.Frame(self.root, bg="#0c0a16")
        btn_frame.pack(fill="x", padx=16, pady=10)

        self._btn(btn_frame, "▶  Start everything", self.start_all, primary=True).pack(
            fill="x", pady=4
        )
        row = tk.Frame(btn_frame, bg="#0c0a16")
        row.pack(fill="x", pady=4)
        self._btn(row, "Open on PC", self.open_local).pack(side="left", expand=True, fill="x", padx=(0, 4))
        self._btn(row, "Copy phone link", self.copy_public).pack(side="left", expand=True, fill="x", padx=(4, 0))
        self._btn(btn_frame, "■  Stop", self.stop_all, danger=True).pack(fill="x", pady=4)
        self._btn(btn_frame, "⚙  Run self-test", self.run_selftest).pack(fill="x", pady=4)

        tip = tk.Label(
            self.root,
            text="Start → share the yellow APP link once\n"
            "Friends open it → join from Public list or room code\n"
            "(No same Wi‑Fi. Keep this window open while hosting.)",
            fg="#7a7098",
            bg="#0c0a16",
            font=("Segoe UI", 9),
            justify="center",
        )
        tip.pack(pady=(4, 12))

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _btn(self, parent, text, cmd, primary=False, danger=False):
        bg = "#5a2fd0" if primary else ("#5a2030" if danger else "#1c1730")
        fg = "#ffffff" if primary or danger else "#e8dfff"
        return tk.Button(
            parent,
            text=text,
            command=cmd,
            bg=bg,
            fg=fg,
            activebackground="#7a4dff" if primary else "#2a2440",
            activeforeground="#fff",
            relief="flat",
            font=("Segoe UI", 11, "bold" if primary else "normal"),
            cursor="hand2",
            padx=10,
            pady=8,
        )

    def set_status(self, text: str, ok: bool = True) -> None:
        self.status.configure(text=text, fg="#6dffa8" if ok else "#ff8a9a")

    def ensure_tools(self) -> bool:
        if not VENV_PY.is_file():
            self.set_status("Missing .venv — run once: python3 -m venv .venv && .venv/bin/pip install websockets", ok=False)
            return False
        if not SERVER.is_file():
            self.set_status("Missing multiplayer/server.py", ok=False)
            return False
        if not CLOUDFLARED.is_file():
            self.set_status("Downloading cloudflared…")
            self.root.update_idletasks()
            try:
                CLOUDFLARED.parent.mkdir(parents=True, exist_ok=True)
                url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
                urllib.request.urlretrieve(url, CLOUDFLARED)
                CLOUDFLARED.chmod(0o755)
            except Exception as e:
                self.set_status(f"cloudflared download failed: {e}", ok=False)
                return False
        return True

    def free_port(self) -> None:
        try:
            subprocess.run(
                ["fuser", "-k", f"{PORT}/tcp"],
                capture_output=True,
                timeout=5,
            )
            time.sleep(0.4)
        except Exception:
            pass

    def start_all(self) -> None:
        if self.server_proc and self.server_proc.poll() is None:
            self.set_status("Already running")
            return
        if not self.ensure_tools():
            return

        def work():
            try:
                self.root.after(0, lambda: self.set_status("Starting server…"))
                self.free_port()
                self.server_proc = subprocess.Popen(
                    [str(VENV_PY), str(SERVER), "--host", "0.0.0.0", "--port", str(PORT)],
                    cwd=str(ROOT),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                # wait until health ok
                for _ in range(40):
                    if self.server_proc.poll() is not None:
                        out = self.server_proc.stdout.read() if self.server_proc.stdout else ""
                        raise RuntimeError(f"Server exited early.\n{out[:400]}")
                    try:
                        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1) as r:
                            if r.status == 200:
                                break
                    except Exception:
                        time.sleep(0.25)
                else:
                    raise RuntimeError("Server did not become ready")

                self.root.after(0, lambda: self.set_status("Server up — starting phone tunnel…"))

                self.tunnel_proc = subprocess.Popen(
                    [str(CLOUDFLARED), "tunnel", "--url", f"http://127.0.0.1:{PORT}", "--no-autoupdate"],
                    cwd=str(ROOT),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                url = self._wait_for_tunnel_url(timeout=45)
                if not url:
                    raise RuntimeError("Tunnel started but no public URL yet — check internet")

                self.public_url = url.rstrip("/") + "/chipbox.html"
                phone_test = url.rstrip("/") + "/phone-test.html"

                def ui_ok():
                    self.link_public.delete(0, tk.END)
                    self.link_public.insert(0, self.public_url)
                    self.set_status(
                        "Live! Share the YELLOW app link once.\n"
                        "Friends open that site → Public list or room code.\n"
                        f"Phone: {self.public_url}\n"
                        f"Test: {phone_test}"
                    )
                    # Auto-open on PC (Windows Chrome)
                    self.open_url(f"http://127.0.0.1:{PORT}/chipbox.html")

                self.root.after(0, ui_ok)
            except Exception as e:
                self.root.after(0, lambda: self.set_status(str(e), ok=False))
                self.stop_all()

        threading.Thread(target=work, daemon=True).start()

    def _wait_for_tunnel_url(self, timeout: float = 45) -> str:
        if not self.tunnel_proc or not self.tunnel_proc.stdout:
            return ""
        deadline = time.time() + timeout
        buf = ""
        # cloudflared prints URL to stdout/stderr combined
        pattern = re.compile(r"https://[a-zA-Z0-9.-]+\.trycloudflare\.com")
        while time.time() < deadline:
            if self.tunnel_proc.poll() is not None:
                rest = self.tunnel_proc.stdout.read() or ""
                buf += rest
                m = pattern.search(buf)
                return m.group(0) if m else ""
            line = self.tunnel_proc.stdout.readline()
            if not line:
                time.sleep(0.05)
                continue
            buf += line
            m = pattern.search(line) or pattern.search(buf)
            if m:
                return m.group(0)
        m = pattern.search(buf)
        return m.group(0) if m else ""

    def open_url(self, url: str) -> None:
        """Open URL in Windows browser (WSL webbrowser often does nothing)."""
        errors: list[str] = []

        # 1) Windows Chrome / Edge via known paths
        win_browsers = [
            "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
            "/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe",
            str(Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe").replace(
                str(Path.home()), "/mnt/c/Users/" + os.environ.get("USER", "seven")
            ),
            "/mnt/c/Users/seven/AppData/Local/Google/Chrome/Application/chrome.exe",
            "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
            "/mnt/c/Program Files/Microsoft/Edge/Application/msedge.exe",
        ]
        for browser in win_browsers:
            if Path(browser).is_file():
                try:
                    subprocess.Popen(
                        [browser, url],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    self.set_status(f"Opened in browser:\n{url}")
                    return
                except Exception as e:
                    errors.append(str(e))

        # 2) cmd.exe start (default Windows association)
        for cmd in (
            ["/mnt/c/Windows/System32/cmd.exe", "/c", "start", "", url],
            ["cmd.exe", "/c", "start", "", url],
        ):
            try:
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.set_status(f"Opened via Windows:\n{url}")
                return
            except Exception as e:
                errors.append(str(e))

        # 3) wslview / xdg-open / webbrowser fallback
        for args in (
            ["wslview", url],
            ["xdg-open", url],
        ):
            try:
                subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.set_status(f"Opened:\n{url}")
                return
            except Exception as e:
                errors.append(str(e))

        try:
            webbrowser.open(url)
            self.set_status(f"Tried default webbrowser:\n{url}")
            return
        except Exception as e:
            errors.append(str(e))

        self.set_status(
            "Couldn't auto-open browser. Paste this in Chrome:\n" + url,
            ok=False,
        )

    def open_local(self) -> None:
        # Prefer local if server is up; else public link if we have one
        url = f"http://127.0.0.1:{PORT}/chipbox.html"
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1) as r:
                if r.status != 200:
                    raise RuntimeError("not ready")
        except Exception:
            if self.public_url:
                url = self.public_url
            else:
                self.set_status(
                    "Server not running — press Start everything first.\n"
                    f"Or paste in Chrome: {url}",
                    ok=False,
                )
                # still try open local in case health check flaked
        self.open_url(url)

    def copy_to_clipboard(self, text: str) -> bool:
        """Copy text so Windows apps can paste (WSL tk clipboard often fails)."""
        text = (text or "").strip()
        if not text:
            return False
        errors: list[str] = []

        # 1) Windows clip.exe (most reliable from WSL)
        for clip in (
            "/mnt/c/Windows/System32/clip.exe",
            "clip.exe",
        ):
            try:
                p = subprocess.run(
                    [clip],
                    input=text,
                    text=True,
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
                if p.returncode == 0:
                    return True
                errors.append(f"clip:{p.returncode}")
            except Exception as e:
                errors.append(str(e))

        # 2) PowerShell Set-Clipboard
        ps = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
        if Path(ps).is_file():
            try:
                p = subprocess.run(
                    [
                        ps,
                        "-NoProfile",
                        "-Command",
                        "Set-Clipboard -Value $input",
                    ],
                    input=text,
                    text=True,
                    capture_output=True,
                    timeout=8,
                    check=False,
                )
                if p.returncode == 0:
                    return True
                errors.append(f"ps:{p.returncode}")
            except Exception as e:
                errors.append(str(e))

        # 3) Tk clipboard (Linux / WSLg)
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update_idletasks()
            self.root.update()
            return True
        except Exception as e:
            errors.append(str(e))

        self.set_status("Copy failed — select the yellow link and Ctrl+C\n" + "; ".join(errors[:2]), ok=False)
        return False

    def copy_public(self) -> None:
        url = (self.public_url or self.link_public.get() or "").strip()
        if not url or url.startswith("("):
            self.set_status(
                "No phone link yet — press Start everything and wait for Live!",
                ok=False,
            )
            return
        # keep entry in sync
        try:
            self.link_public.delete(0, tk.END)
            self.link_public.insert(0, url)
        except Exception:
            pass
        if self.copy_to_clipboard(url):
            self.set_status("Phone link copied — paste on your phone\n" + url)

    def stop_all(self) -> None:
        for proc in (self.tunnel_proc, self.server_proc):
            if proc and proc.poll() is None:
                try:
                    proc.send_signal(signal.SIGTERM)
                except Exception:
                    pass
                try:
                    proc.kill()
                except Exception:
                    pass
        self.tunnel_proc = None
        self.server_proc = None
        self.free_port()
        self.public_url = ""
        self.link_public.delete(0, tk.END)
        self.link_public.insert(0, "(public phone link appears after Start)")
        self.set_status("Stopped")


    def run_selftest(self) -> None:
        def work():
            try:
                self.root.after(0, lambda: self.set_status("Running self-test…"))
                # ensure server up first
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1)
                except Exception:
                    self.root.after(0, lambda: self.set_status("Start everything first, then self-test", ok=False))
                    return
                r = subprocess.run(
                    [str(VENV_PY), str(ROOT / "multiplayer" / "selftest.py"), f"http://127.0.0.1:{PORT}"],
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                out = (r.stdout or "") + (r.stderr or "")
                # keep last lines
                lines = [ln for ln in out.strip().splitlines() if ln.strip()]
                summary = "\n".join(lines[-8:]) if lines else "no output"
                ok = r.returncode == 0
                self.root.after(0, lambda: self.set_status(("Self-test OK\n" if ok else "Self-test FAILED\n") + summary, ok=ok))
            except Exception as e:
                self.root.after(0, lambda: self.set_status(f"Self-test error: {e}", ok=False))
        threading.Thread(target=work, daemon=True).start()

    def on_close(self) -> None:
        self.stop_all()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    # Prefer DISPLAY for GUI
    if not os.environ.get("DISPLAY"):
        os.environ["DISPLAY"] = ":0"
    Launcher().run()


if __name__ == "__main__":
    main()
