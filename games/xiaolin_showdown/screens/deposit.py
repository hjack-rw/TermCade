"""Deposit screen — cash a chosen hand card for its points, then back to the vault.

A deposit-power Wu prompts first: banking it forfeits the power, so you confirm. Crossing the
point limit with a deposit ends the run at once.
"""

from __future__ import annotations

from typing import cast

from termcade.ui.work import work
from textual.app import ComposeResult
from textual.widgets import Footer, Header, Static

from termcade.ui.screens.base import EngineScreen
from termcade.ui.widgets import BoxedPanel, Button

from ..logic.actions import deposit
from ..logic.turn import VAULT
from ..logic.mechanics.powers import is_gamble, trigger_of
from ..logic.models import Card
from ..logic.settings import XiaolinSettings
from ..logic.state import XiaolinState
from .format import card_label, points_label, your_move


class DepositScreen(EngineScreen):
    BINDINGS = [("escape", "app.pop_screen", "Cancel")]

    def compose(self) -> ComposeResult:
        state = cast(XiaolinState, self.ctx.state)
        yield Header()
        with BoxedPanel(title="VAULT"):
            yield Static("Choose a card", classes="panel-desc")
            for index, card in enumerate(state.player.hand):
                # `points_label`, not `card.points`: the gamble Wu is worth `?` and must read as one
                # here too, or the button quietly tells you what the card refuses to.
                yield Button(card_label(card, f"   +{points_label(card)} pts"), id=f"dep-{index}")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        assert event.button.id is not None
        state = cast(XiaolinState, self.ctx.state)
        self._choose(state.player.hand[int(event.button.id.removeprefix("dep-"))])

    @work
    async def _choose(self, card: Card) -> None:
        if trigger_of(card.power) == "use":  # banking it forfeits its power — confirm first
            # Name the power the Wu actually has. The joke Wu's is "? ? ?" in the card DB, and that
            # is the right thing to print: you are being asked to give up something unnamed.
            forfeit = await self.confirm(
                f"This Wu has a power: {card.power.name}. Forfeit it for points?",
                title="FORFEIT",
                yes="Yes, forfeit for points",
                no="No, keep it",
            )
            if not forfeit:
                return
        self._bank(card)

    def _bank(self, card: Card) -> None:
        state = cast(XiaolinState, self.ctx.state)
        paid = deposit(state, card, rng=self.ctx.rng)
        if is_gamble(card.power):  # you banked a "? ? ?" — this is the moment you learn what it was
            # Its own toast is the record: it says what the Wu turned out to be worth, which is more
            # than a generic "banked" line, and two entries for one deposit would just be noise.
            self.app.notify(_gamble_result(card, paid), title="? ? ?")
        else:
            # A deposit raises no toast — you watch the points move — so the log would lose the most
            # common action in the game.
            self.ctx.journal.add(
                f"You deposited {card.name} for {paid} pts.", title=your_move(VAULT)
            )
        settings = XiaolinSettings.from_settings(self.ctx.settings.current)
        if state.player.points >= settings.point_limit:  # crossing the line ends the game at once
            state.has_ended = True
            from .outcome import OutcomeScreen

            self.app.switch_screen(OutcomeScreen())
        else:
            self.app.pop_screen()


def _gamble_result(card: Card, paid: int) -> str:
    """What the mystery Wu turned out to be worth. It can cost you, so say which it did."""
    if paid > 0:
        return f"{card.name} was worth {paid} pt{'s' if paid != 1 else ''}!"
    if paid == 0:
        return f"{card.name} was worth nothing at all."
    return f"{card.name} cost you {abs(paid)} pt{'s' if paid != -1 else ''}!"
