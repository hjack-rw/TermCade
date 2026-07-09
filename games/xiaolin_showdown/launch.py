"""Desktop launcher — play in the browser with no terminal, no Docker, no install.

Double-clicking the built executable runs this: it starts the local ``serve`` server and opens the
default browser at it, so the player never sees a command line. Plain ``serve`` stays headless (for
Docker). Frozen into a standalone exe (PyInstaller), this same file is *also* what textual-serve runs
for each browser session — invoked with ``--run-game`` it boots the game directly, so the bundle
needs no separate ``xiaolin`` command on the machine.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import webbrowser

_LOG = os.path.join(tempfile.gettempdir(), "termcade-launch.log")


def _log(message: str) -> None:
    """Append a line to a launch log, so a GUI double-click that fails silently still leaves a trace
    of how far it got and any traceback (``%TEMP%\\termcade-launch.log``)."""
    try:
        with open(_LOG, "a", encoding="utf-8") as handle:
            handle.write(message + "\n")
    except OSError:
        pass


def _run_game() -> None:
    """Boot the game itself — the per-session child that textual-serve pipes to the browser."""
    from termcade.ui.app import EngineApp

    from .game import build_game

    EngineApp(build_game()).run()


def _free_port() -> int:
    """An OS-assigned free port. Deliberately *not* a fixed default like 8000 — that races with a
    Django dev server (or anything on a common port): both can momentarily think it's free and then
    fight over it, killing our server. The launcher opens the browser itself, so the number is unseen."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))  # port 0 -> the OS hands back a guaranteed-free port
        return sock.getsockname()[1]


def _chromium_exe() -> str | None:
    """Path to Edge or Chrome for a clean maximized app window, or ``None``. Resolved from the
    Windows registry's ``App Paths`` — where every browser's installer records its exe — so it holds
    up regardless of install location or Windows UI language, not a hard-coded ``Program Files`` guess."""
    if sys.platform == "win32":  # the guard also tells mypy winreg is safe here (Windows-only module)
        import winreg

        for exe in ("msedge.exe", "chrome.exe"):
            for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    key = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}"
                    with winreg.OpenKey(root, key) as handle:
                        path, _ = winreg.QueryValueEx(handle, "")  # "" = the (Default) value = exe path
                except OSError:
                    continue
                if path and os.path.isfile(path):
                    return path
    return shutil.which("msedge") or shutil.which("chrome")


def _open_browser(url: str) -> None:
    """Open the game. Prefer a Chromium browser in maximized *app* mode — a clean, obvious foreground
    window that clears the size gate — launched via ``Popen`` (``CreateProcess``, unlike
    ``os.startfile``'s ``ShellExecute`` it is dependable from a background thread under a GUI launch).
    Fall back to the default browser only if no Chromium browser is present."""
    try:
        exe = _chromium_exe()
        _log(f"browser: exe={exe!r}")
        if exe is not None:
            # A dedicated profile forces a *fresh* browser instance — otherwise `--app` is forwarded
            # to Edge's always-on background processes and no window appears.
            profile = os.path.join(tempfile.gettempdir(), "termcade-browser")
            subprocess.Popen([exe, f"--app={url}", "--start-maximized", f"--user-data-dir={profile}"])
            _log("browser: launched app window")
            return
        opener = getattr(os, "startfile", None)
        if opener is not None:
            opener(url)
            _log("browser: os.startfile")
        else:
            webbrowser.open(url)
            _log("browser: webbrowser")
    except Exception:  # noqa: BLE001 - a failed opener must never take down the server thread
        _log("browser ERROR:\n" + traceback.format_exc())


def _open_when_ready(url: str, port: int) -> None:
    """Wait until the server actually accepts a connection, then open the browser — so the window
    never beats the server (a blank page that self-closes) on a slow start."""
    for _ in range(80):  # up to ~20s
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.25)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                _log("server ready; opening browser")
                _open_browser(url)
                return
        time.sleep(0.25)
    _log("server not ready after 20s; opening browser anyway")
    _open_browser(url)


def main() -> None:
    if "--run-game" in sys.argv:  # a per-session child spawned by textual-serve
        _run_game()
        return

    try:
        open(_LOG, "w", encoding="utf-8").close()  # fresh log each launch
        _log("=== launch ===")
        from termcade import serve

        port = int(os.environ["PORT"]) if os.environ.get("PORT") else _free_port()
        # 127.0.0.1, not "localhost": Windows resolves localhost to IPv6 ::1 first, but the server
        # binds IPv4 — the mismatch leaves the browser on a blank page. A literal IPv4 URL avoids it.
        url = f"http://127.0.0.1:{port}"
        _log(f"port={port} frozen={getattr(sys, 'frozen', False)}")
        # Frozen exe: textual-serve re-invokes this same exe (via the shell) to run each session's
        # game. From source: the installed ``xiaolin`` console script.
        game = f'"{sys.executable}" --run-game' if getattr(sys, "frozen", False) else "xiaolin"

        if not os.environ.get("TERMCADE_NO_BROWSER"):  # the flag lets tests serve headlessly
            threading.Thread(target=_open_when_ready, args=(url, port), daemon=True).start()
        print(f"TermCade is starting — your browser will open at {url}")
        print("Keep this window open while you play; close it to stop.")
        _log("serving")
        # Size the page from the cartridge's own descriptor, so the browser can't disagree with it.
        from .game import build_game

        card = build_game()
        serve.make_server(
            port=port,
            public_url=url,
            game=game,
            host="127.0.0.1",
            fit_size=card.fit_size or serve.DEFAULT_FIT_SIZE,
            min_size=card.min_size,
        ).serve()
        _log("serve() returned (server stopped)")
    except Exception:
        _log("MAIN ERROR:\n" + traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
