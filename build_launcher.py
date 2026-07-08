"""Build the standalone, double-click TermCade executable with PyInstaller.

    pip install -e ".[build]"
    python build_launcher.py

Produces a single file, ``dist/TermCade.exe`` — hand it to anyone, put it anywhere, double-click. No
Python, no Docker, no terminal: it starts the browser build locally and opens it. A small console
window shows the URL and stays open as the stop button.

Notes
- ``--onefile``: ONE movable .exe. A onedir build is a folder that must keep its ``_internal`` beside
  the exe — trivially broken by copying just the .exe (or clicking the one in ``build/``) — so this
  ships a single file at the cost of a brief self-unpack on launch (and per textual-serve session).
- ``--collect-all`` pulls each package's submodules *and* data files — the card DB, the icon font,
  the TCSS themes, and textual-serve's xterm.js assets — so nothing is missing at runtime.
"""

from __future__ import annotations

import PyInstaller.__main__

PyInstaller.__main__.run(
    [
        "TermCade.py",
        "--name=TermCade",
        "--onefile",
        "--noconfirm",
        "--console",  # prints the URL; closing it stops the server
        "--collect-all=textual",
        "--collect-all=textual_serve",
        "--collect-all=aiohttp",
        "--collect-all=xiaolin_showdown",
        "--collect-all=termcade",
    ]
)
