"""A screen that rebuilds itself must not lose the line that says how to use it.

`refresh(recompose=True)` tears down the `Footer` and builds a new one — and the new one comes up
EMPTY, because it fills itself from the screen's bindings as it mounts and there are none to read yet.
Nothing errors. The screen still works. It just silently stops telling anyone which keys it takes, and
the vault recomposes on every return from a sub-screen, so looking one card up cost you the hint line
for the rest of the run.

`EngineScreen.rebuild` is the recompose that puts it back. This is the test that says so.
"""

from __future__ import annotations

from textual.widgets import Button, Footer

from termcade.ui.screens.base import EngineScreen


class _Rebuilding(EngineScreen):
    BINDINGS = [("1", "one", "One"), ("2", "two", "Two")]

    def compose(self):
        yield Button("rebuild me", id="go")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.rebuild()


def _keys(app) -> list[str]:
    return [key.key for key in app.screen.query_one(Footer).query("FooterKey")]


async def test_a_rebuilt_screen_still_advertises_its_keys(make_app):
    app = make_app(_Rebuilding)
    async with app.run_test() as pilot:
        # The Footer fills itself a frame after it mounts — usually one pause, but not guaranteed
        # under load, so poll instead of trusting a fixed wait (this is what made the suite flaky).
        for _ in range(10):
            await pilot.pause()
            if _keys(app):
                break
        before = _keys(app)
        assert {"1", "2"} <= set(before)

        await pilot.click("#go")
        for _ in range(10):
            await pilot.pause()
            if _keys(app) == before:
                break

        assert _keys(app) == before
