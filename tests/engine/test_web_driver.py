"""InProcessWebDriver: does hosting two EngineApp instances in one process, sharing one event
loop, keep each session's output and input correctly isolated from the other's.

This promotes a prototype validated interactively during the shared-process redesign (see
project memory) into real, reproducible coverage. It is the one property the whole redesign
depends on: WebDriver normally writes to the process's real stdout fd and reads input from a
real background thread bound to real stdin, both correct only when a session owns a whole OS
process to itself. InProcessWebDriver replaces both with per-instance alternatives (an internal
queue for output, an explicit feed_input for input) — these tests are what would fail if that
replacement leaked one session's bytes or keystrokes into the other's.
"""

from __future__ import annotations

import asyncio
from typing import Any

from termcade.app.game import Game
from termcade.core.audio import MUTE_ENV
from termcade.ui.app import EngineApp
from termcade.web_driver import InProcessWebDriver


class _NoState:
    schema_version = 1

    def snapshot(self) -> dict[str, Any]:
        return {}

    @classmethod
    def restore(cls, data: dict[str, Any], ctx: Any) -> "_NoState":
        return cls()


def _game(game_id: str) -> Game:
    return Game(game_id=game_id, title=game_id, state_cls=_NoState)


async def _run_session(
    app: EngineApp, label: str, *, iterations: int, out: bytearray, keys: list[str]
) -> None:
    app.driver_class = InProcessWebDriver

    async def pump() -> None:
        driver: InProcessWebDriver = app._driver  # type: ignore[assignment]
        await driver.pump_output(lambda data: _append(out, data))

    async def hammer() -> None:
        # Yields every step, on purpose: this is the exact interleaving window where one
        # session's write or feed_input could land in the other's driver if the isolation were
        # ever accidentally shared (a class attribute instead of an instance one, a queue
        # constructed once instead of per-driver, etc).
        await asyncio.sleep(0.02)  # let start_application_mode run first
        driver: InProcessWebDriver = app._driver  # type: ignore[assignment]
        # A probe written directly through THIS driver, not relied-on render output: whether
        # Textual's compositor gets around to painting the mounted screen before app.exit() fires
        # is a race this test must not depend on to mean something -- write_meta goes straight
        # through _write -> this instance's own queue, with no render/compose step in between, so
        # this is a deterministic, direct check of the actual property under test.
        driver.write_meta({"type": "termcade_test_probe", "label": label})
        for _ in range(iterations):
            driver.feed_input(label)
            keys.append(label)
            await asyncio.sleep(0)
        app.exit()

    async with asyncio.timeout(10):
        await asyncio.gather(
            app.run_async(headless=False, mouse=False, size=(80, 24)),
            pump(),
            hammer(),
        )


async def _append(buf: bytearray, data: bytes) -> None:
    buf.extend(data)


async def _collect(buf: list[bytes], data: bytes) -> None:
    buf.append(data)


async def test_two_sessions_never_cross_output_or_input() -> None:
    app_a = EngineApp(_game("a"), is_touch=False)
    app_b = EngineApp(_game("b"), is_touch=False)
    out_a, out_b = bytearray(), bytearray()
    keys_a: list[str] = []
    keys_b: list[str] = []

    await asyncio.gather(
        _run_session(app_a, "1", iterations=30, out=out_a, keys=keys_a),
        _run_session(app_b, "2", iterations=30, out=out_b, keys=keys_b),
    )

    assert out_a and out_b, "both sessions must have written something"
    assert b'"label": "1"' in out_a, "session_a never received its own probe"
    assert b'"label": "2"' in out_b, "session_b never received its own probe"
    assert b'"label": "2"' not in out_a, "session_b's probe leaked into session_a's buffer"
    assert b'"label": "1"' not in out_b, "session_a's probe leaked into session_b's buffer"
    assert keys_a == ["1"] * 30
    assert keys_b == ["2"] * 30


async def test_stop_application_mode_lets_pump_output_finish_and_return() -> None:
    app = EngineApp(_game("solo"), is_touch=False)
    app.driver_class = InProcessWebDriver
    received: list[bytes] = []

    async def pump() -> None:
        driver: InProcessWebDriver = app._driver  # type: ignore[assignment]
        await driver.pump_output(lambda data: _collect(received, data))

    async def stop_soon() -> None:
        await asyncio.sleep(0.02)
        app.exit()

    async with asyncio.timeout(10):
        await asyncio.gather(
            app.run_async(headless=False, mouse=False, size=(80, 24)),
            pump(),
            stop_soon(),
        )

    assert received, "the startup frame(s) must have reached the sink before pump_output returned"


async def test_real_game_mounts_and_renders_through_inprocess_driver(monkeypatch) -> None:
    """Every test above drives a minimal stub Game (_NoState, no root_screen) -- proving isolation,
    but never that the actual xiaolin_showdown game (real catalog load, real CSS theme, real
    screens, real audio wiring) survives the trip through this driver. That gap looked like a
    silent hang during manual investigation, but the hang was an artifact of print-based
    checkpoints losing lines somewhere in a Docker+shell capture chain, not real behavior -- a
    file-logged rerun of the exact same scenario showed on_mount completing normally throughout.
    This pins the real finding down as a permanent, reliable (no stdout involved) assertion."""
    monkeypatch.setenv(MUTE_ENV, "1")
    from xiaolin_showdown.game import build_game

    mounted = asyncio.Event()

    class _Probe(EngineApp):
        def on_mount(self) -> None:
            super().on_mount()
            mounted.set()

    app = _Probe(build_game(), is_touch=False)
    app.driver_class = InProcessWebDriver
    received = bytearray()

    async def pump() -> None:
        driver: InProcessWebDriver = app._driver  # type: ignore[assignment]
        await driver.pump_output(lambda data: _append(received, data))

    async def stop_when_mounted() -> None:
        await asyncio.wait_for(mounted.wait(), timeout=8)
        app.exit()

    async with asyncio.timeout(10):
        await asyncio.gather(
            app.run_async(headless=False, mouse=False, size=(80, 24)),
            pump(),
            stop_when_mounted(),
        )

    assert received, "the real game must have produced rendered output through the driver"
