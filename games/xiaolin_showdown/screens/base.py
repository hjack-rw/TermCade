"""The cartridge's screen bases: the run and its rules, without the ceremony."""

from __future__ import annotations

from typing import cast

from termcade.ui.screens.base import EngineScreen
from termcade.ui.screens.menu import MenuScreen

from ..logic.config.settings import XiaolinSettings
from ..logic.schema.state import XiaolinState


class _Run:
    """The live run, typed. The engine's ``ctx.state`` is an opaque `GameState` and its settings are a
    flat dict — every screen was casting one and re-viewing the other on entry."""

    @property
    def state(self) -> XiaolinState:
        return cast(XiaolinState, self.ctx.state)  # type: ignore[attr-defined]

    @property
    def rules(self) -> XiaolinSettings:
        """This run's settings — rebuilt per read, because a screen may have just changed them."""
        return XiaolinSettings.from_settings(self.ctx.settings.current)  # type: ignore[attr-defined]

    def end_run(self) -> None:
        """Flag the run over, advance the boss ladder on a win, and show the outcome.

        Scored once, here: `final_score` rolls any gamble Wu still in hand, and computing it twice
        would roll it twice, disagreeing with itself. `OutcomeScreen` is handed the result rather
        than recomputing it. Lazy imports: outcome.py imports the temple.
        """
        self.state.has_ended = True
        from ..logic.config.ladder import record_win
        from ..logic.flow.outcome import final_score
        from .run.outcome import OutcomeScreen

        outcome = final_score(self.state, self.ctx.rng)  # type: ignore[attr-defined]
        if outcome.winner is self.state.player.character:
            settings = self.ctx.settings.current  # type: ignore[attr-defined]
            boss = self.state.bot.character if self.state.boss_run else None
            updated = record_win(settings, difficulty=settings.difficulty, boss=boss)
            if updated is not settings:
                self.ctx.settings.save(updated)  # type: ignore[attr-defined]
        self.app.switch_screen(OutcomeScreen(outcome))  # type: ignore[attr-defined]


class XiaolinScreen(_Run, EngineScreen):
    """A screen that composes its own layout."""


class XiaolinMenu(_Run, MenuScreen):
    """A screen that is a titled panel of buttons — see `MenuScreen`. Supply the title, the items, and
    what a press does."""
