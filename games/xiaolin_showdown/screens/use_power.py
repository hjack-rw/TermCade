"""Powers — spend a Wu for its power (no points), then back to the vault.

The Conch asks a question back, so firing a power runs in a worker that can await a modal: the logic
layer cannot ask, it takes the answer as an argument.
"""

from __future__ import annotations

from rich.text import Text
from termcade.ui.screens.menu import MenuItem
from termcade.ui.work import work

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
from ..logic.turn import EARLY_BIRD, POWER
from .base import XiaolinMenu
from .format import card_headline, card_label, power_headline, your_move

NOTHING_COMING = "The pile is empty — nothing is coming."


class UsePowerScreen(XiaolinMenu):
    """The Early Bird is listed among the Wu powers: it costs the same action and spends a Wu, so it
    is a power like any other — it just belongs to no card."""

    BINDINGS = [("escape", "app.pop_screen", "Cancel")]

    menu_title = "POWERS"
    menu_description = "Choose a power"

    def menu_items(self) -> list[MenuItem]:
        self._usable: list[Card] = usable_powers(self.state, self.rules.actions_per_turn)
        items = [
            MenuItem(id=f"pow-{index}", label=power_headline(card))
            for index, card in enumerate(self._usable)
        ]
        if can_early_bird(self.state, self.rules):
            items.append(MenuItem(id="early-bird", label=EARLY_BIRD))
        return items

    def on_select(self, item_id: str) -> None:
        if item_id == "early-bird":
            self._fly()
            return
        self._spend(self._usable[int(item_id.removeprefix("pow-"))])

    @work
    async def _fly(self) -> None:
        """The Early Bird: take the next Wu with no duel, paying one of your fastest for it."""
        asked = Text("Take the next Wu with no duel.")
        asked.append("\n\n")  # statement, blank line, question — the shape every dialog uses
        asked.append("Which Initiative Wu do you give up?")

        surrendered = await self.choose(
            asked,
            [(card_label(card), card) for card in early_bird_options(self.state)],
            title="THE EARLY BIRD",
        )
        if surrendered is None:
            return
        message = early_bird(self.state, surrendered)
        self.app.pop_screen()
        self.app.notify(message, log=False)  # the log gets the move's own shape, below
        self.ctx.journal.add(
            f"You used Early Bird and sacrificed {surrendered.name}.",
            title=your_move(EARLY_BIRD),
        )

    @work
    async def _spend(self, card: Card) -> None:
        mechanic = mechanic_of(card.power)
        priority = await self._ask_priority() if mechanic is Mechanic.TELEPATHEIA else None
        target = await self._ask_target(mechanic)

        message = use_power(self.state, card, priority=priority, target=target, rng=self.ctx.rng)
        self.app.pop_screen()
        self.app.notify(message, log=False)
        self.ctx.journal.add(
            f"You played {card.power.name} from the {card.name}.\n{message}",
            title=your_move(POWER),
        )

    async def _ask_target(self, mechanic: Mechanic) -> Card | None:
        """The Wu a power is aimed at. Both lists are ones the player may read: their own deck, and
        the opponent's hand (already face up on the vault board)."""
        if mechanic is Mechanic.ATTRACTION:
            return await self.choose(
                "Pull which Wu from your deck?",
                [(card_label(wu), wu) for wu in self.state.player.deck],
                title="GLOVE OF JISAKU",
            )
        if mechanic is Mechanic.REPULSION:
            return await self.choose(
                "Shove which Wu out of their hand? They will deposit it.",
                [(card_label(wu), wu) for wu in self.state.bot.hand],
                title="RUBY OF RAMSES",
            )
        return None

    async def _ask_priority(self) -> bool:
        """Reveal and question on one screen: the next Wu is the whole reason to want initiative, so
        choosing before seeing it would be no choice at all."""
        coming = coming_wu(self.state)
        heard = Text()
        if coming:
            heard.append_text(card_headline(coming[0]))
            heard.append(" comes next.")
        else:
            heard.append(NOTHING_COMING)
        heard.append("\n\n")
        heard.append("Take Initiative in the next Showdown?")

        return await self.confirm(heard, title="MIND READER CONCH", yes="Take it", no="Refuse it")
