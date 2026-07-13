"""A crashed worker must be loud. Textual's default is silence, and silence is a trap.

Every decision a screen asks a player for runs in a `@work` method — the deposit confirm, the Morpher's
element, the Early Bird's price. An exception inside one is swallowed whole: the worker dies, the screen
sits there, and the game looks like it ignored the key.

That is not hypothetical. A missing import in `deposit.py` once made "deposit a Wu" do nothing at all,
and it read as a *game* bug for as long as it took to find the real cause. This is the test that would
have found it in a second.
"""

from __future__ import annotations

import pytest
from textual.widgets import Button

from termcade.app.game import Game
from termcade.core.settings import Settings
from termcade.ui.app import EngineApp
from termcade.ui.screens.base import EngineScreen
from termcade.ui.screens.dialog import ChoiceModal
from termcade.ui.work import work


class _Doomed(EngineScreen):
    """A screen whose one action explodes inside a worker — the shape of the real bug."""

    def compose(self):
        yield Button("do the thing", id="go")

    def on_button_pressed(self) -> None:
        self._explode()

    @work
    async def _explode(self) -> None:
        raise RuntimeError("the deposit screen forgot an import")


@pytest.fixture
def app(tmp_path):
    game = Game(
        game_id="crash-test",
        title="Crash",
        state_cls=None,
        default_settings=Settings(),
        saves_enabled=False,
        root_screen=_Doomed,
    )
    return EngineApp(game, data_dir=tmp_path, seed=1)


async def test_a_crash_inside_a_worker_reaches_the_player(app):
    async with app.run_test() as pilot:
        await pilot.pause()

        await pilot.click("#go")
        for _ in range(20):  # the worker dies asynchronously; the dialog follows it
            await pilot.pause()
            if isinstance(pilot.app.screen, ChoiceModal):
                break

        assert isinstance(pilot.app.screen, ChoiceModal), "the worker died in silence"


async def test_the_crash_names_the_error_rather_than_shrugging(app):
    """"Something went wrong" is worth nothing. The exception's name and message are the whole value."""
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#go")
        for _ in range(20):
            await pilot.pause()
            if isinstance(pilot.app.screen, ChoiceModal):
                break

        shown = str(pilot.app.screen._prompt)  # what the dialog puts in front of the player

        assert "RuntimeError" in shown
        assert "forgot an import" in shown


async def test_a_healthy_worker_raises_no_dialog(app):
    """The alarm has to be silent when nothing is wrong, or nobody will believe it when it is not."""
    async with app.run_test() as pilot:
        await pilot.pause()

        for _ in range(5):
            await pilot.pause()

        assert not isinstance(pilot.app.screen, ChoiceModal)
