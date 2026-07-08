"""Deposit screen — cash a chosen hand card for its points, then back to the vault.

A deposit-power Wu prompts first: banking it forfeits the power, so you confirm. Crossing the
point limit with a deposit ends the run at once.
"""

from __future__ import annotations

from typing import cast

from textual.app import ComposeResult
from textual.widgets import Button, Footer, Header, Static

from termcade.ui.screens.base import EngineScreen
from termcade.ui.widgets import BoxedPanel

from ..logic.actions import deposit
from ..logic.models import Card
from ..logic.settings import XiaolinSettings
from ..logic.state import XiaolinState
from .duel import ChoiceModal


class DepositScreen(EngineScreen):
    BINDINGS = [("escape", "app.pop_screen", "Cancel")]

    def compose(self) -> ComposeResult:
        state = cast(XiaolinState, self.ctx.state)
        yield Header()
        with BoxedPanel(title="DEPOSIT"):
            yield Static("Choose a card", classes="panel-desc")
            for index, card in enumerate(state.player.hand):
                yield Button(f"{card.name}   +{card.points} pts", id=f"dep-{index}")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        assert event.button.id is not None
        state = cast(XiaolinState, self.ctx.state)
        card = state.player.hand[int(event.button.id.removeprefix("dep-"))]
        if card.power.trigger == "deposit":  # banking it forfeits its power — confirm first
            self.app.push_screen(
                ChoiceModal(
                    "This Wu has a power on Deposit — forfeit it for points?",
                    [("Yes, forfeit for points", True), ("No, keep it", False)],
                    title="FORFEIT",
                ),
                lambda forfeit: self._bank(card) if forfeit else None,
            )
        else:
            self._bank(card)

    def _bank(self, card: Card) -> None:
        state = cast(XiaolinState, self.ctx.state)
        deposit(state, card)
        settings = XiaolinSettings.from_settings(self.ctx.settings.current)
        if state.player.points >= settings.point_limit:  # crossing the line ends the game at once
            state.has_ended = True
            from .outcome import OutcomeScreen

            self.app.switch_screen(OutcomeScreen())
        else:
            self.app.pop_screen()
