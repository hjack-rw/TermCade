"""The cartridge's screen base: the run and its rules, without the ceremony."""

from __future__ import annotations

from typing import cast

from termcade.ui.screens.base import EngineScreen

from ..logic.settings import XiaolinSettings
from ..logic.state import XiaolinState


class XiaolinScreen(EngineScreen):
    """An `EngineScreen` that knows it is holding a Xiaolin run.

    The engine's `ctx.state` is an opaque `GameState` and `ctx.settings` is a flat dict view — every
    screen was casting one and re-viewing the other on entry (18 and 11 times respectively).
    """

    @property
    def state(self) -> XiaolinState:
        return cast(XiaolinState, self.ctx.state)

    @property
    def rules(self) -> XiaolinSettings:
        """This run's frozen settings — a typed view, rebuilt each read (a screen may change them)."""
        return XiaolinSettings.from_settings(self.ctx.settings.current)

    def end_run(self) -> None:
        """Flag the run over and show the outcome. Lazy import: outcome.py imports the vault."""
        self.state.has_ended = True
        from .outcome import OutcomeScreen

        self.app.switch_screen(OutcomeScreen())
