"""Use-a-Power screen — spend a Wu on its power (drawing, revealing, or nothing), then back to the
vault.

Distinct from Deposit: this fires the Wu's power and discards it for *no* points, where Deposit
banks it for its points. The result (a draw, a glimpse, or the gag Wu's fizzle) shows as a toast.

One power asks a question back. The Mind Reader Conch shows the next Wu in the pile and then wants
an answer — initiative in the next showdown, or not — so firing it runs in a worker that can wait
on a modal. The logic layer cannot ask: it takes the answer as an argument.
"""

from __future__ import annotations

from typing import cast

from termcade.ui.work import work
from textual.app import ComposeResult
from textual.widgets import Footer, Header, Static

from termcade.ui.screens.base import EngineScreen
from termcade.ui.widgets import BoxedPanel, Button

from ..logic.actions import (
    can_early_bird,
    coming_wu,
    early_bird,
    early_bird_options,
    usable_powers,
    use_power,
)
from ..logic.mechanics.powers import Mechanic, mechanic_of
from ..logic.models import Card
from ..logic.settings import XiaolinSettings
from ..logic.state import XiaolinState
from .format import card_label, trigger_label

NOTHING_COMING = "The pile is empty — nothing is coming."

# The Early Bird is not a Wu, but it is a power: it costs the turn's action, it spends a Wu, and it is
# offered only while it can actually be used. So it belongs on this screen, listed under the Wu whose
# powers can be spent — not as a menu action of its own.
EARLY_BIRD_LABEL = "The Early Bird"
EARLY_BIRD_HINT = "   (outrun them to the next Wu)"


class UsePowerScreen(EngineScreen):
    BINDINGS = [("escape", "app.pop_screen", "Cancel")]

    def compose(self) -> ComposeResult:
        state = cast(XiaolinState, self.ctx.state)
        settings = XiaolinSettings.from_settings(self.ctx.settings.current)
        self._usable: list[Card] = usable_powers(state, settings.actions_per_turn)
        self._early_bird = can_early_bird(state, settings)

        yield Header()
        with BoxedPanel(title="USE A POWER"):
            yield Static("Choose a Wu", classes="panel-desc")
            for index, card in enumerate(self._usable):
                yield Button(card_label(card, f"   ({trigger_label(card.power)})"), id=f"pow-{index}")
            if self._early_bird:
                yield Button(f"{EARLY_BIRD_LABEL}{EARLY_BIRD_HINT}", id="early-bird")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        assert event.button.id is not None
        if event.button.id == "early-bird":
            self._fly()
            return
        self._spend(self._usable[int(event.button.id.removeprefix("pow-"))])

    @work
    async def _fly(self) -> None:
        """The Early Bird: take the next Wu with no duel, and give up one of your fastest for it."""
        state = cast(XiaolinState, self.ctx.state)

        surrendered = await self.choose(
            "Take the next Wu with no duel. Which initiative Wu do you give up?",
            [(card_label(card), card) for card in early_bird_options(state)],
            title="THE EARLY BIRD",
        )
        if surrendered is None:
            return
        message = early_bird(state, surrendered)
        self.app.pop_screen()
        self.app.notify(message)

    @work
    async def _spend(self, card: Card) -> None:
        state = cast(XiaolinState, self.ctx.state)
        mechanic = mechanic_of(card.power)

        priority = await self._ask_priority(state) if mechanic is Mechanic.TELEPATHEIA else None
        target = await self._ask_target(state, mechanic)

        message = use_power(state, card, priority=priority, target=target, rng=self.ctx.rng)
        self.app.pop_screen()
        self.app.notify(message)

    async def _ask_target(self, state: XiaolinState, mechanic: Mechanic) -> Card | None:
        """The Wu a power is aimed at — your own deck to pull from, or their hand to shove.

        Both are the player's pick, and both are lists they are allowed to read: your deck is yours,
        and their hand is already face up on the vault board.
        """
        if mechanic is Mechanic.ATTRACTION:
            return await self.choose(
                "Pull which Wu from your deck?",
                [(card_label(wu), wu) for wu in state.player.deck],
                title="GLOVE OF JISAKU",
            )
        if mechanic is Mechanic.REPULSION:
            return await self.choose(
                "Shove which Wu out of their hand? They will bank it.",
                [(card_label(wu), wu) for wu in state.bot.hand],
                title="RUBY OF RAMSES",
            )
        return None

    async def _ask_priority(self, state: XiaolinState) -> bool:
        """Show what the Conch hears, then take the answer it was spent for.

        The reveal and the question are one screen on purpose: the next Wu is the whole reason to
        want initiative — or to hand it over — so being told it *after* choosing would be no help.
        """
        coming = coming_wu(state)
        heard = f"{coming[0].name} comes next." if coming else NOTHING_COMING
        return await self.confirm(
            f"{heard} Take initiative in the next showdown?",
            title="MIND READER CONCH",
            yes="Take it",
            no="Refuse it",
        )
