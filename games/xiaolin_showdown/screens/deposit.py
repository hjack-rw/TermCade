"""Deposit — cash a hand Wu for its points. A `use`-power Wu confirms first (banking forfeits the
power). Crossing the point limit ends the run at once."""

from __future__ import annotations

from termcade.ui.work import work
from textual.app import ComposeResult
from textual.widgets import Footer, Header, Static

from termcade.ui.widgets import BoxedPanel, Button

from ..logic.actions import deposit
from ..logic.mechanics.powers import is_gamble, trigger_of
from ..logic.models import Card
from ..logic.turn import VAULT
from .base import XiaolinScreen
from .format import card_label, points_label, your_move


class DepositScreen(XiaolinScreen):
    BINDINGS = [("escape", "app.pop_screen", "Cancel")]

    def compose(self) -> ComposeResult:
        yield Header()
        with BoxedPanel(title="VAULT"):
            yield Static("Choose a card", classes="panel-desc")
            for index, card in enumerate(self.state.player.hand):
                # `points_label`, never `card.points`: the gamble Wu is worth `?` and reads as one.
                yield Button(card_label(card, f"   +{points_label(card)} pts"), id=f"dep-{index}")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        assert event.button.id is not None
        self._choose(self.state.player.hand[int(event.button.id.removeprefix("dep-"))])

    @work
    async def _choose(self, card: Card) -> None:
        if trigger_of(card.power) == "use":  # banking it forfeits the power — ask first
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
        paid = deposit(self.state, card, rng=self.ctx.rng)
        if is_gamble(card.power):
            # The reveal IS the record — it says what the `?` turned out to be worth.
            self.app.notify(_gamble_result(card, paid), title="? ? ?")
        else:
            # A deposit raises no toast (you watch the points move), so the log must be told.
            self.ctx.journal.add(f"You deposited {card.name} for {paid} pts.", title=your_move(VAULT))

        if self.state.player.points >= self.rules.point_limit:
            self.end_run()
        else:
            self.app.pop_screen()


def _gamble_result(card: Card, paid: int) -> str:
    """What the mystery Wu paid. It can cost you, so say which it did."""
    if paid > 0:
        return f"{card.name} was worth {paid} pt{'s' if paid != 1 else ''}!"
    if paid == 0:
        return f"{card.name} was worth nothing at all."
    return f"{card.name} cost you {abs(paid)} pt{'s' if paid != -1 else ''}!"
