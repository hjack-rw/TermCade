"""The Game Log — the screen that gives a player back the toast they missed.

A notification shows for a few seconds in a corner and the game does not pause while it is up. These
pin the two promises that make the log worth opening: **everything** the game said is in it, and it is
the record of *this* run and no other.
"""

from __future__ import annotations

from typing import Any

from rich.text import Text

from termcade.ui.screens.base import EngineScreen
from termcade.ui.screens.log import EMPTY, GameLogScreen


class FakeState:
    """Any state at all — the log cares that one was dealt, never what is in it."""

    schema_version = 1

    def snapshot(self) -> dict[str, Any]:
        return {}

    @classmethod
    def restore(cls, data: dict[str, Any], ctx: Any) -> "FakeState":
        return cls()


class _Root(EngineScreen):
    def compose(self):
        return iter(())


async def test_every_notification_is_written_down(make_app):
    """The engine's own funnel: a game that raises a toast gets a log entry for free."""
    app = make_app(_Root)
    async with app.run_test() as pilot:
        app.ctx.state = FakeState()
        app.notify("Drew Eagle Scope.")
        await pilot.pause()

        assert [entry.message for entry in app.ctx.journal.entries] == ["Drew Eagle Scope."]


async def test_a_new_run_opens_on_an_empty_log(make_app):
    """A record of a run must be a record of *that* run — dealing a state empties what came before."""
    app = make_app(_Root)
    async with app.run_test() as pilot:
        app.ctx.state = FakeState()
        app.notify("Something from the run before.")
        await pilot.pause()

        app.ctx.state = FakeState()  # a new game, or a save loaded over the top of one

        assert len(app.ctx.journal) == 0


async def test_the_screen_shows_what_was_said_and_what_it_was_about(make_app):
    app = make_app(_Root)
    async with app.run_test() as pilot:
        app.ctx.state = FakeState()
        app.notify("They banked the Sphere.", title="Opponent's move")
        await pilot.pause()

        await app.push_screen(GameLogScreen())
        await pilot.pause()

        shown = app.screen.showing
        assert "Opponent's move" in shown
        assert "They banked the Sphere." in shown


async def test_the_lines_gather_under_the_turn_they_happened_in(make_app):
    """The turn is the unit a player thinks in — a flat scroll cannot answer "what did they do last
    turn?", which is the question the log is opened to answer."""
    app = make_app(_Root)
    async with app.run_test() as pilot:
        app.ctx.state = FakeState()
        app.notify("An early move.")
        app.ctx.journal.next_turn()
        app.notify("A later move.")
        await pilot.pause()

        await app.push_screen(GameLogScreen())
        await pilot.pause()

        shown = app.screen.showing
        assert shown.index("Turn 1") < shown.index("An early move.") < shown.index("Turn 2")
        assert shown.index("Turn 2") < shown.index("A later move.")


async def test_the_game_draws_its_own_nouns(make_app):
    """The engine cannot know what a Wu is — a cartridge hands it the brush (`Game.log_line`)."""
    app = make_app(_Root, log_line=lambda line: Text(line.upper()))
    async with app.run_test() as pilot:
        app.ctx.state = FakeState()
        app.notify("they played bras finger")
        await pilot.pause()

        await app.push_screen(GameLogScreen())
        await pilot.pause()

        assert "THEY PLAYED BRAS FINGER" in app.screen.showing


async def test_the_screen_says_so_when_nothing_has_happened(make_app):
    app = make_app(_Root)
    async with app.run_test() as pilot:
        app.ctx.state = FakeState()
        await app.push_screen(GameLogScreen())
        await pilot.pause()

        assert app.screen.showing == EMPTY
