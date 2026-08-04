"""Powers — spend a Wu for its power (no points), then back to the temple.

The Conch asks a question back, so firing a power runs in a worker that can await a modal: the logic
layer cannot ask, it takes the answer as an argument.
"""

from __future__ import annotations

from copy import deepcopy

from rich.text import Text
from termcade.ui.screens.menu import MenuItem
from termcade.ui.work import work

from ...logic.flow.actions import (
    can_combine_yoyo,
    can_construct,
    can_early_bird,
    can_self_correct_yoyo,
    coming_wu,
    combine_yoyo,
    construct_jong,
    early_bird,
    early_bird_options,
    self_correct_yoyo,
    usable_powers,
    use_power,
)
from ...logic.schema.constants import YIN_YANG_YOYO_ID
from ...logic.mechanics.powers import Mechanic, mechanic_of
from ...logic.schema.models import Card
from ...logic.config.settings import player_actions
from ...logic.flow.turn import EARLY_BIRD, POWER
from ..base import XiaolinMenu
from ..display.format import card_options, prompt
from ..display.headline import card_headline, power_headline, your_move

NOTHING_COMING = "The pile is empty — nothing is coming."
CONSTRUCT = "Construct Mala Mala Jong"
COMBINE_YOYO = "Combine into Yin-Yang Yo-Yo"
SELF_CORRECT_YOYO = "Correct Your Own Alignment"


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
        # The set is complete: offer the transform. Its own entry, not a Wu spend — it consumes the
        # whole hand's worth, not one card, so it reads as the momentous thing it is.
        if can_construct(self.state, player_actions(self.state, self.rules)):
            items.append(MenuItem(id="construct", label=CONSTRUCT))
        budget = player_actions(self.state, self.rules)
        if can_combine_yoyo(self.state, budget):
            items.append(MenuItem(id="combine-yoyo", label=COMBINE_YOYO))
        if can_self_correct_yoyo(self.state, budget):
            items.append(MenuItem(id="self-correct-yoyo", label=SELF_CORRECT_YOYO))
        return items

    def on_select(self, item_id: str) -> None:
        if item_id == "early-bird":
            self._fly()
            return
        if item_id == "construct":
            self._construct()
            return
        if item_id == "combine-yoyo":
            self._combine_yoyo()
            return
        if item_id == "self-correct-yoyo":
            self._self_correct_yoyo()
            return
        self._spend(self._usable[self.index_of(item_id, "pow")])

    def _return_to_temple(self, toast: str, log_line: str, action: str) -> None:
        """Every power-worker ends the same way: pop back to the temple, flash a toast that must NOT
        self-log (``log=False`` — the journal owns the log's shape), then journal the outcome. One
        place, so a forgotten ``log=False`` cannot double-log a mangled toast into the Game Log."""
        self.app.pop_screen()
        self.engine_app.notify(toast, log=False)
        self.ctx.journal.add(log_line, title=your_move(action))

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
        message = early_bird(self.state, surrendered, rng=self.ctx.rng)  # rng lets a Mouse undo it
        self._return_to_temple(
            message,
            f"You used Early Bird to take {taken.name}, giving up {surrendered.name}.",
            EARLY_BIRD,
        )

    @work
    async def _construct(self) -> None:
        """Become Mala Mala Jong: keep the body and the wudai, exile the Heart, bank the rest."""
        purged = construct_jong(self.state, is_player=True)
        banked = f" {len(purged)} Wu banked." if purged else ""
        self._return_to_temple(
            f"You assembled Mala Mala Jong.{banked}",
            "You constructed Mala Mala Jong — a 6/6/6 body of Shen Gong Wu.\n"
            "Reach the end of the game in the form to win outright.",
            POWER,
        )

    @work
    async def _combine_yoyo(self) -> None:
        """Fuse the two Yo-Yo halves into the Ying-Yang Yo-Yo — never drawn on its own, only ever
        built this way (see `logic.constants.in_pool`)."""
        combined = deepcopy(self.state.catalog.card(YIN_YANG_YOYO_ID))
        combine_yoyo(self.state, combined, is_player=True)
        self._return_to_temple(
            "You combined your Yo-Yo halves into the Ying-Yang Yo-Yo.",
            "You combined Ying Yo-Yo and Yang Yo-Yo into the Ying-Yang Yo-Yo.",
            POWER,
        )

    @work
    async def _self_correct_yoyo(self) -> None:
        """Spend the combined Ying-Yang Yo-Yo to flip your own affiliation back — exiled for good,
        the same as a Treasurebox's wish."""
        self_correct_yoyo(self.state, is_player=True)
        self._return_to_temple(
            "It's hard to spot the difference, isn't it?",
            "You spent the Ying-Yang Yo-Yo to correct your own alignment.",
            POWER,
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
        # the log drops the power name — the line here already gives it — and keeps only the outcome
        self._return_to_temple(
            report.toast, f"You played {card.power.name} from the {card.name}.\n{report.log}", POWER
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
        if mechanic is Mechanic.WISH:
            return await self.choose(
                "Wish which Wu out of the Vault? (theirs is the prize)",
                card_options(self.state.player.vault + self.state.bot.vault),
                title="TREASUREBOX",
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
