"""Duel screen — one showdown, driven by the async :class:`~..logic.duel.Duel` stage machine.

The stage machine awaits the player's decisions; here each ``await`` raises a :class:`ChoiceModal`
via ``push_screen_wait`` and resolves with the chosen value. The whole showdown runs in an async
worker so the UI stays responsive and the pure game logic never touches Textual.

One press of "Gong Yi Tanpai" plays exactly one showdown (stages 1→6→0). The temple turn runs here
too, at the end — you shelve any surplus Wu, the bot takes its turn, and the hands settle — so
control returns to the temple, or, when the draw pile is spent, to the :class:`~.outcome.OutcomeScreen`.
"""

from __future__ import annotations

import asyncio

from rich.text import Text
from termcade.ui.work import work
from textual.app import ComposeResult
from textual.content import ContentText
from textual.widgets import Footer, Header, Static

from termcade.ui.widgets import BoxedPanel, TooltipStatic

from ..logic.duel import COMMITMENT, END, SETUP, Duel, DuelChoices, DuelState
from ..logic.constants import ELEMENTS, TOURNAMENT
from ..logic.models import Card
from ..logic.settings import XiaolinSettings
from ..logic.state import XiaolinState
from ..logic.turn import bot_turn, max_hand_size, refill_hands, shelve
from .base import XiaolinScreen
from .duel_board import _board_text, _showdown_story, _wager_label
from .rules import RulesScreen
from .format import (
    SHOWDOWN_LOG,
    opponent_move,
    card_options,
    display_name,
    element_text,
)


class DuelScreen(XiaolinScreen):
    """One showdown, stepped through a phase at a time — the player presses Continue to advance,
    seeing each phase resolve, and the choice phases raise their modal inline."""

    # Rules is a binding and nothing more: it never joins the prompt line, because that line is the
    # duel's *move* list and looking something up is not a move. It costs no turn and changes no
    # state, so it stays available for the whole showdown, long after Retreat has stopped being.
    BINDINGS = [
        ("enter,space", "continue", "Continue"),
        ("8", "rules", "Rules"),
        ("escape", "retreat", "Retreat"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._continue = asyncio.Event()
        self._duel: Duel | None = None
        self._retreating = False
        self._committed = False  # once the showdown begins there is no walking away

    def compose(self) -> ComposeResult:
        yield Header()
        with BoxedPanel(title="XIAOLIN SHOWDOWN", id="duel-panel"):
            yield TooltipStatic("Gong Yi Tanpai!", id="duel-body")
            yield Static("", id="duel-prompt")
        yield Footer()

    def on_mount(self) -> None:
        self._run_showdown()

    def action_continue(self) -> None:
        self._continue.set()

    def action_rules(self) -> None:
        """Put the rulebook on screen. The showdown underneath is mid-await on ``_continue`` and
        simply keeps waiting — nothing is advanced, nothing is skipped, and the key is dead while a
        choice modal is up, because a modal owns the input while it is the active screen."""
        self.app.push_screen(RulesScreen())

    def action_retreat(self) -> None:
        """Back out before the showdown begins — return to the temple.

        Only the opening board offers this: from the first "Continue" the priority is locked (or the
        coin is thrown) and the prize is drawn, so there is nothing left to walk away from.
        """
        if self._committed:
            # Not logged: this is a *refusal*, an answer to a key, not something that happened in the
            # run. A log full of the game saying no is a log nobody reads.
            self.engine_app.notify("Gong Yi Tanpai! There is no retreat from a showdown.", log=False)
            return
        self._retreating = True
        self._continue.set()

    async def _await_continue(self, prompt: str) -> None:
        self.query_one("#duel-prompt", Static).update(f"▶  {prompt}")
        self._continue.clear()
        await self._continue.wait()
        self.query_one("#duel-prompt", Static).update("")

    async def _reveal_coin_toss(self, player_won: bool) -> None:
        """Tied initiative — the player calls the coin, then learns whether they hold priority."""
        call = await self.choose(
            "Tied initiative —  call the coin.",  # the em-dash eats the space to its right
            [("Heads", "heads"), ("Tails", "tails")],
            title="COIN TOSS",
        )
        # Priority was already decided; reveal a face consistent with it — a matching call wins.
        face = call if player_won else ("tails" if call == "heads" else "heads")
        outcome = "You win priority!" if player_won else "You lose priority!"
        await self.show_message(f"The coin lands {face.upper()}.  {outcome}", title="COIN TOSS")

    def _announce_wager(self, duel: DuelState, state: XiaolinState) -> None:
        """You called the challenge, so your opponent sets the price — and names it to your face."""
        name = display_name(state.bot.character.name)
        self.engine_app.notify(
            # Not logged: the showdown's own story tells who staked what, in the order it happened.
            # Logging it here as well would say the same thing twice, once out of order.
            f"{name} requested a {_wager_label(duel.wager)}",
            title="The stakes",
            log=False,
        )

    @work
    async def _run_showdown(self) -> None:
        state, settings, rng = self.state, self.rules, self.ctx.rng

        duel = Duel(state, rng, self._choices(), settings)
        self._duel = duel

        # Initiative is already on the board: this press commits you to the priority you can see, or
        # (on a tie) draws the coin that settles it. It is the last moment you may walk away.
        self._show_board(duel)
        await self._await_continue("Continue to begin the showdown        Esc Retreat")
        if self._retreating:
            self._retreat_to_temple()
            return
        self._committed = True

        while True:
            stage = await duel.advance()  # one phase; a choice phase raises its modal inline
            self._show_board(duel)
            if stage == COMMITMENT and duel.duel.player.initiative == duel.duel.bot.initiative:
                await self._reveal_coin_toss(duel.duel.player_priority is True)
            # They set the price only if you called a *stat*. A tournament prices itself — three
            # battles of one Wu — so there is nothing they named and nothing to announce.
            if stage == SETUP and duel.duel.player_priority and duel.duel.challenge != TOURNAMENT:
                self._announce_wager(duel.duel, state)
            if stage == END:  # the end phase (the loser's stakes change hands) has run
                break
            await self._await_continue("Continue")

        # The result raises no toast — it is written across the board, and a toast over it would be
        # telling a player what they are looking at. But the board is gone the moment they leave, so
        # the one thing a showdown is *for* would be the one thing the log could not tell them.
        #
        # It is the LAST line of the turn it was fought in, and it belongs to neither duelist: a
        # showdown is not somebody's move, it is what the two moves were leading to.
        self.ctx.journal.add(_showdown_story(duel.duel, state), title=SHOWDOWN_LOG)

        # The result is already on screen, so head straight into the temple turn (no extra Continue):
        # you shelve any surplus Wu (your choice), the bot banks points, then the
        # hands settle (which may flag the run over on the point limit). Skip once the pile is spent.
        if not state.has_ended:
            await self._discard_surplus(state, settings)
            # The showdown closed the turn. What follows is the *next* one opening — starting with
            # their half of it, which is why the log must be cut here and not after.
            self.ctx.journal.next_turn()
            # Their half of the temple turn that is about to open. The first turn of a run has no
            # showdown in front of it, so that one is taken at character select instead.
            difficulty = self.ctx.settings.current.difficulty  # the bot's deposit skill follows it
            moves = bot_turn(state, settings, rng=rng, difficulty=difficulty)
            self.app.notify(
                "\n".join(move.line for move in moves),
                title=opponent_move([move.action for move in moves]),
            )
            state.bot_turn_done = True
            refill_hands(state, settings, rng=rng)
        self._leave()

    async def _discard_surplus(self, state: XiaolinState, settings: XiaolinSettings) -> None:
        """Over the hand limit (you just won cards) → choose which Wu to shelve to your deck."""
        while not state.has_ended:
            if len(state.player.whole_hand) <= max_hand_size(state.player, settings.max_hand_size):
                return
            card = await self.choose(
                "Too many Wu —  shelve one to your deck",
                card_options(state.player.hand, suffix_stats=True),
                title="DISPOSE",
            )
            state.player.remove_card(card)
            shelve(state.player, card, rng=self.ctx.rng)

    def _leave(self) -> None:
        if self.state.has_ended:
            self.end_run()
        else:
            self._retreat_to_temple()

    def _retreat_to_temple(self) -> None:
        """Abandon an uncommitted showdown — no prize drawn, no cards staked, nothing to undo."""
        from .temple import TempleScreen

        self.app.switch_screen(TempleScreen())

    def _show_board(self, duel: Duel) -> None:
        self.query_one("#duel-body", TooltipStatic).update(
            _board_text(duel.duel, self.state)
        )

    # --- player decisions: raise a modal, resolve with what they pick ---------------------
    def _choices(self) -> DuelChoices:
        return DuelChoices(
            challenge=self._pick_challenge,
            background=self._pick_background,
            wager=self._pick_wager,
            boost=self._pick_boost,
            card=self._pick_card,
            element=self._pick_element,
            stat=self._pick_stat,
        )

    async def _pick_challenge(self, options: list[str]) -> str:
        return await self.choose(
            "Name the challenge —  one stat, or all three.",
            _stat_options(options),
            title="CHALLENGE",
        )

    async def _pick_background(self, options: list[str]) -> str:
        return await self.choose("Choose the background element", _element_options(options), title="BACKGROUND")

    async def _pick_wager(self, options: list[int]) -> int:
        """They named the stat; you name how wide the battle is. Both hands are face up — read them.

        Never asked on a tournament: three battles of one Wu is the whole of it, and there is nothing
        left to price.
        """
        if len(options) == 1:
            return options[0]  # nothing to decide: one of you can only field the one Wu
        return await self.choose(
            "They called the Showdown. How many Wu will you wager?",
            [(_wager_label(n), n) for n in options],
            title="THE STAKES",
        )

    async def _pick_element(self, _background: str) -> str:
        return await self.choose("Choose an element", _element_options(list(ELEMENTS)), title="ELEMENT")

    async def _pick_stat(self, options: list[str]) -> str:
        """Where the Orb's flood, or the Curse's misfortune, lands.

        The contested stat is worth double, so it is the obvious answer — but the other two are worth
        a point each, and taking both of them wins the battle just the same. That is the whole card.
        """
        return await self.choose("Which stat do you name?", _stat_options(options), title="NAME A STAT")

    async def _pick_boost(self, cards: list[Card]) -> Card | None:
        options: list[tuple[ContentText, Card | None]] = [
            *card_options(cards, suffix_stats=True),
            ("Don't play", None),
        ]
        return await self.choose("Play a boost Wu?", options, title="BOOST")

    async def _pick_card(self, cards: list[Card]) -> Card:
        """Field a Wu, blind. Your opponent is choosing theirs against the same board you see."""
        if self._duel is not None:
            self._show_board(self._duel)
        return await self.choose("Play a card", card_options(cards, suffix_stats=True), title="CARD")


def _stat_options(values: list[str]) -> list[tuple[str, str]]:
    return [(value.upper(), value) for value in values]


def _element_options(values: list[str]) -> list[tuple[Text, str]]:
    """An element names itself in its own colour, on a button as on the board."""
    return [(_upper(element_text(value)), value) for value in values]


def _upper(text: Text) -> Text:
    upper = Text(text.plain.upper(), style=text.style)
    upper.spans = list(text.spans)
    return upper
