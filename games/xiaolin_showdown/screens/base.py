"""The cartridge's screen bases: the run and its rules, without the ceremony."""

from __future__ import annotations

from typing import cast

from termcade.ui.screens.base import EngineScreen
from termcade.ui.screens.menu import MenuScreen

from ..logic.settings import XiaolinSettings
from ..logic.state import XiaolinState


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
        """Flag the run over and show the outcome. Lazy import: outcome.py imports the vault."""
        self.state.has_ended = True
        from .outcome import OutcomeScreen

        self.app.switch_screen(OutcomeScreen())  # type: ignore[attr-defined]


class XiaolinScreen(_Run, EngineScreen):
    """A screen that composes its own layout."""


class XiaolinMenu(_Run, MenuScreen):
    """A screen that is a titled panel of buttons — see `MenuScreen`. Supply the title, the items, and
    what a press does."""
