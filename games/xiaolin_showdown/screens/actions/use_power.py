"""Powers — spend a Wu for its power (no points), then back to the temple.

The Conch asks a question back, so firing a power runs in a worker that can await a modal: the logic
layer cannot ask, it takes the answer as an argument.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy

from rich.text import Text
from termcade.ui.screens.menu import MenuItem
from termcade.ui.work import work
from textual.widgets import Static

from ...logic.flow.actions import (
    can_combine_yoyo,
    can_construct,
    can_early_bird,
    can_farsight,
    can_self_correct_yoyo,
    coming_wu,
    combine_yoyo,
    construct_jong,
    early_bird,
    early_bird_options,
    farsight,
    self_correct_yoyo,
    usable_powers,
    use_power,
)
from ...logic.characters.jong import PART_TYPES
from ...logic.schema.constants import YIN_YANG_YOYO_ID
from ...logic.mechanics.powers import SCOPE_DEPTH, Mechanic, mechanic_of
from ...logic.schema.models import Card
from ...logic.config.settings import player_actions
from ...logic.flow.turn import EARLY_BIRD, POWER
from ..base import XiaolinMenu
from ..display.format import card_name_text, card_options, prompt
from ..display.headline import card_headline, power_headline, your_move

NOTHING_COMING = "The pile is empty — nothing is coming."
CONSTRUCT = "Construct Mala Mala Jong"
COMBINE_YOYO = "Combine into Yin-Yang Yo-Yo"
SELF_CORRECT_YOYO = "Correct Your Own Alignment"
FARSIGHT = "Farsight: Reorder the Coming Wu"


def _ordinal(position: int) -> str:
    """1st, 2nd, 3rd, 4th... — as many places as Farsight ever needs to ask for."""
    if 10 <= position % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(position % 10, "th")
    return f"{position}{suffix}"


def _assembly_order(hand: list[Card]) -> list[Card]:
    """The Wu locking into Mala Mala Jong, in slot order (head, torso, arms, boots, amulet), the
    Heart last. Mirrors ``jong._one_of_each_part``/``_is_heart`` — those stay private to the logic
    module, so the display-only ordering is kept here rather than reaching in for them."""
    found: dict[str, Card] = {}
    for card in hand:
        if card.type in PART_TYPES and card.type not in found:
            found[card.type] = card
    assert len(found) == len(PART_TYPES), "_assembly_order called without a full set — gate with can_construct first"
    heart = next((card for card in hand if mechanic_of(card.power) is Mechanic.ANIMATE), None)
    assert heart is not None, "_assembly_order called without a Heart — gate with can_construct first"
    return [found[slot] for slot in PART_TYPES] + [heart]


class UsePowerScreen(XiaolinMenu):
    """The Early Bird is listed among the Wu powers — same action cost, but belongs to no card."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    menu_title = "POWERS"
    menu_description = "Choose a power"

    def __init__(self) -> None:
        super().__init__()
        # Set once `_construct` commits its irreversible mutation, so Escape can't pop this screen
        # out from under the still-running assembly animation — see `_construct`/`action_cancel`.
        self._committing = False

    def action_cancel(self) -> None:
        if self._committing:
            # Not logged: a refusal isn't something that happened in the run.
            self.engine_app.notify(
                "Mala Mala Jong is assembling — that's irreversible.",
                log=False,
                severity="warning",
            )
            return
        self.app.pop_screen()

    def menu_items(self) -> list[MenuItem]:
        # One button per distinct power. Two identical Wu (two Eagle Scopes) spend the same and read
        # the same, so a second row is only noise — collapse by name, and `_spend` fires one copy.
        seen: set[str] = set()
        self._usable: list[Card] = []
        for card in usable_powers(self.state, player_actions(self.state, self.rules), self.rules):
            if card.name not in seen:
                seen.add(card.name)
                self._usable.append(card)
        items = [
            MenuItem.indexed("pow", index, power_headline(card))
            for index, card in enumerate(self._usable)
        ]
        if can_early_bird(self.state, self.rules):
            items.append(MenuItem(id="early-bird", label=EARLY_BIRD))
        # Its own entry, not a Wu spend — it consumes the whole hand's worth, not one card.
        if can_construct(self.state, player_actions(self.state, self.rules)):
            items.append(MenuItem(id="construct", label=CONSTRUCT))
        budget = player_actions(self.state, self.rules)
        if can_combine_yoyo(self.state, budget):
            items.append(MenuItem(id="combine-yoyo", label=COMBINE_YOYO))
        if can_self_correct_yoyo(self.state, budget):
            items.append(MenuItem(id="self-correct-yoyo", label=SELF_CORRECT_YOYO))
        if can_farsight(self.state, budget):
            items.append(MenuItem(id="farsight", label=FARSIGHT))
        return items

    def on_select(self, item_id: str) -> None:
        if item_id == "early-bird":
            self._fly()
            return
        if item_id == "construct":
            self._construct()
            return
        if item_id == "farsight":
            self._farsight()
            return
        if item_id == "combine-yoyo":
            self._combine_yoyo()
            return
        if item_id == "self-correct-yoyo":
            self._self_correct_yoyo()
            return
        self._spend(self._usable[self.index_of(item_id, "pow")])

    def _return_to_temple(self, toast: str, log_line: str, action: str) -> None:
        """Every power-worker ends the same way: pop back to the temple, flash a toast that never
        self-logs, then journal the outcome. Centralized so a forgotten ``log=False`` can't
        double-log a toast.

        Flags the Temple underneath (always this screen's pusher — see `TempleScreen.action_use_power`)
        so its next resume gives the Actions panel a beat of colour too — a toast alone is easy to
        miss, and unlike the toast this reads from the screen the player is looking at."""
        temple = self.app.screen_stack[-2]
        from ..run.temple import TempleScreen  # lazy: temple.py imports this module at the top level

        if isinstance(temple, TempleScreen):
            temple.flag_power_used()
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
        # Captured before `construct_jong` empties the hand down to the kept parts and the wudai.
        parts = _assembly_order(self.state.player.hand)
        purged = construct_jong(self.state, is_player=True)
        # Irreversible past this point — block Escape so it can't pop the screen out from under the
        # animation while this worker is still mid-flight (see `action_cancel`).
        self._committing = True
        banked = f" {len(purged)} Wu banked." if purged else ""
        await self._show_assembly(parts)
        self._return_to_temple(
            f"You assembled Mala Mala Jong.{banked}",
            "You constructed Mala Mala Jong — a 6/6/6 body of Shen Gong Wu.\n"
            "Reach the end of the game in the form to win outright.",
            POWER,
        )

    async def _show_assembly(self, parts: list[Card]) -> None:
        """The five slots locking in, then the Heart, one Wu at a time — each named in its own
        element colour, the same as everywhere else a Wu is shown. A generic fill bar wouldn't say
        *what* just assembled."""
        desc = self.query_one(".panel-desc", Static)
        lines = Text()
        for card in parts:
            if lines.plain:
                lines.append("\n")
            lines.append_text(card_name_text(card))
            desc.update(lines.copy())
            await asyncio.sleep(0.25)
        await asyncio.sleep(0.2)
        desc.update(Text("MALA MALA JONG!", style="bold"))
        await asyncio.sleep(0.3)

    @work
    async def _farsight(self) -> None:
        """Falcon's Eye and Eagle Scope together: see as far down the pile as Teleskopia ever could,
        then set what you saw back down in whatever order you choose — both Wu spent for it."""
        depth = min(SCOPE_DEPTH, len(self.state.card_deck))
        coming = coming_wu(self.state, depth)
        order = await self._ask_order(coming)
        if order is None:
            return
        farsight(self.state, order, self.rules, is_player=True)
        seen = ", ".join(card.name for card in order)
        self._return_to_temple(
            "You saw as far down the pile as your sister Wu could see, and set it back down your own way.",
            f"You spent Falcon's Eye and Eagle Scope together and reordered the coming Wu: {seen}.",
            POWER,
        )

    async def _ask_order(self, coming: list[Card]) -> list[Card] | None:
        """One pick at a time — which Wu comes 1st, then which of what's left comes 2nd, and so on —
        until every revealed Wu has a place. `None` if the player backs out partway through."""
        remaining = list(coming)
        order: list[Card] = []
        for position in range(1, len(coming) + 1):
            picked = await self.choose(
                f"Which comes {_ordinal(position)}?",
                card_options(remaining),
                title="FARSIGHT",
            )
            if picked is None:
                return None
            remaining = [card for card in remaining if card is not picked]  # by identity — two Wu
            order.append(picked)  # can print the same face (`cards.is_one_of`'s reason for existing)
        return order

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
            self.state, card, self.rules, priority=priority, target=target, to_deck=to_deck, rng=self.ctx.rng
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
        """Where the shoved Wu lands. Returns True for the deck, False for a deposit."""
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
        """Reveal the next Wu before asking whether to take initiative — choosing blind would be no
        choice at all."""
        coming = coming_wu(self.state)
        if coming:
            top = card_headline(coming[0])
            top.append(" comes next.")
        else:
            top = Text(NOTHING_COMING)
        heard = prompt(top, "Take Initiative in the next Showdown?")

        return await self.confirm(heard, title="MIND READER CONCH", yes="Take it", no="Refuse it")
