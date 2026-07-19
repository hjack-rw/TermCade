"""Powers — spend a Wu for its power (no points), then back to the temple.

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
from ..logic.settings import player_actions
from ..logic.turn import EARLY_BIRD, POWER
from .base import XiaolinMenu
from .format import card_headline, card_options, power_headline, prompt, your_move

NOTHING_COMING = "The pile is empty — nothing is coming."


class UsePowerScreen(XiaolinMenu):
    """The Early Bird is listed among the Wu powers: it costs the same action and spends a Wu, so it
    is a power like any other — it just belongs to no card."""

    BINDINGS = [("escape", "app.pop_screen", "Cancel")]

    menu_title = "POWERS"
    menu_description = "Choose a power"

    def menu_items(self) -> list[MenuItem]:
        # One button per distinct power. Two identical Wu (two Eagle Scopes) spend the same and read
        # the same, so a second row is only noise — collapse by name, and `_spend` fires one copy.
        seen: set[str] = set()
        self._usable: list[Card] = []
        for card in usable_powers(self.state, player_actions(self.state, self.rules)):
            if card.name not in seen:
                seen.add(card.name)
                self._usable.append(card)
        items = [
            MenuItem.indexed("pow", index, power_headline(card))
            for index, card in enumerate(self._usable)
        ]
        if can_early_bird(self.state, self.rules):
            items.append(MenuItem(id="early-bird", label=EARLY_BIRD))
        return items

    def on_select(self, item_id: str) -> None:
        if item_id == "early-bird":
            self._fly()
            return
        self._spend(self._usable[self.index_of(item_id, "pow")])

    @work
    async def _fly(self) -> None:
        """The Early Bird: take the next Wu with no duel, paying one of your fastest for it."""
        surrendered = await self.choose(
            prompt("Take the next Wu with no duel.", "Which Initiative Wu do you give up?"),
            card_options(early_bird_options(self.state)),
            title="THE EARLY BIRD",
        )
        if surrendered is None:
            return
        taken = self.state.card_deck[0]  # the Wu the Early Bird takes, off the top of the pile
        message = early_bird(self.state, surrendered)
        self.app.pop_screen()
        self.engine_app.notify(message, log=False)  # the log gets the move's own shape, below
        self.ctx.journal.add(
            f"You used Early Bird to take {taken.name}, giving up {surrendered.name}.",
            title=your_move(EARLY_BIRD),
        )

    @work
    async def _spend(self, card: Card) -> None:
        mechanic = mechanic_of(card.power)
        priority = await self._ask_priority() if mechanic is Mechanic.ENHANCED_VISION else None
        target = await self._ask_target(mechanic)
        to_deck = await self._ask_destination(target) if mechanic is Mechanic.BOUNCE else False

        report = use_power(
            self.state, card, priority=priority, target=target, to_deck=to_deck, rng=self.ctx.rng
        )
        self.app.pop_screen()
        self.engine_app.notify(report.toast, log=False)  # the toast names the power and sets the scene
        self.ctx.journal.add(
            # the log drops the power name — the line here already gives it — and keeps only the outcome
            f"You played {card.power.name} from the {card.name}.\n{report.log}",
            title=your_move(POWER),
        )

    async def _ask_target(self, mechanic: Mechanic) -> Card | None:
        """The Wu a power is aimed at. Both lists are ones the player may read: their own deck, and
        the opponent's hand (already face up on the temple board)."""
        if mechanic is Mechanic.FETCH:
            return await self.choose(
                "Pull which Wu from your deck?",
                card_options(self.state.player.deck),
                title="GLOVE OF JISAKU",
            )
        if mechanic is Mechanic.BOUNCE:
            return await self.choose(
                "Shove which Wu out of their hand?",
                card_options(self.state.bot.hand),
                title="RUBY OF RAMSES",
            )
        return None

    async def _ask_destination(self, target: Card | None) -> bool:
        """Where the shoved Wu lands — the two costs of Repulsion. Deposit pays them points but is
        forever; the deck gives no points but they draw it back. Returns True for the deck."""
        if target is not None:
            top = card_headline(target)
            top.append(" — where does it go?")
        else:
            top = Text("Where does the shoved Wu go?")
        asked = prompt(top, "Their temple pays them points but is final; their deck pays nothing but returns.")

        return await self.confirm(
            asked,
            title="RUBY OF RAMSES",
            yes="Into their deck",
            no="Deposit for points",
        )

    async def _ask_priority(self) -> bool:
        """Reveal and question on one screen: the next Wu is the whole reason to want initiative, so
        choosing before seeing it would be no choice at all."""
        coming = coming_wu(self.state)
        if coming:
            top = card_headline(coming[0])
            top.append(" comes next.")
        else:
            top = Text(NOTHING_COMING)
        heard = prompt(top, "Take Initiative in the next Showdown?")

        return await self.confirm(heard, title="MIND READER CONCH", yes="Take it", no="Refuse it")
