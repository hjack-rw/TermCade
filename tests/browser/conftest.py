"""A real browser against a real server.

Everything else in the suite tests the page as a STRING. That is worth doing and it is not enough:
the Back button once sent a key xterm.js silently refuses to encode, and every Python test passed
because they press keys straight into Textual and never cross the terminal. These tests are the only
ones that would have caught it.

Marked ``browser`` so a working loop can skip them (``-m "not browser"``); CI runs them.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("playwright", reason="browser tests need playwright")

from playwright.sync_api import Browser, Page, sync_playwright  # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]
# Landscape phone: the shape most of this behaviour was written for, and the one a tester holds.
_VIEWPORT = {"width": 844, "height": 390}
_PHONE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="session")
def served() -> Iterator[str]:
    """The game, served, on a port nobody else holds. One server for the whole module — booting it
    costs seconds and none of these tests mutate it."""
    port = _free_port()
    env = {
        **os.environ,
        "PORT": str(port),
        "PUBLIC_URL": f"http://127.0.0.1:{port}",
        "GAME": "xiaolin",
        "GAME_FACTORY": "xiaolin_showdown.game:build_game",
    }
    env.pop("TERMCADE_MUTE", None)  # these tests are about sound reaching the page
    env.pop("TERMCADE_CODES", None)  # ...and not about the passcode gate
    proc = subprocess.Popen(
        [sys.executable, "-m", "termcade.serve"],
        env=env, cwd=_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(150):  # 30s: a cold import of textual + the game is not instant
            if proc.poll() is not None:
                raise RuntimeError("the server exited before it began serving")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError(f"nothing answered on {url}")
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as pw:
        try:
            b = pw.chromium.launch()
        except Exception as error:  # noqa: BLE001 — no browser binary is a skip, not a failure
            pytest.skip(f"chromium is not installed for playwright: {error}")
        try:
            yield b
        finally:
            b.close()


@pytest.fixture
def phone(browser: Browser, served: str) -> Iterator[Page]:
    """A page that has finished booting the game: terminal up, fonts settled, theme rendered."""
    page = browser.new_page(
        viewport=_VIEWPORT, is_mobile=True, has_touch=True, user_agent=_PHONE_UA
    )
    page.goto(served, wait_until="networkidle")
    page.wait_for_selector(".xterm-screen", timeout=30_000)
    page.wait_for_function("document.fonts.status === 'loaded'", timeout=30_000)
    try:
        yield page
    finally:
        page.close()
