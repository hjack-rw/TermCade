"""Duel screen — one showdown, driven by the async :class:`~..logic.duel.Duel` stage machine.

The stage machine awaits the player's decisions; here each ``await`` raises a :class:`ChoiceModal`
via ``push_screen_wait`` and resolves with the chosen value. The whole showdown runs in an async
worker so the UI stays responsive and the pure game logic never touches Textual.

One press of "Gong Yi Tanpai" plays exactly one showdown, then control returns to the temple, or,
once the draw pile is spent, to :class:`~.outcome.OutcomeScreen`.
"""

from __future__ import annotations

import asyncio

from rich.style import Style
from rich.text import Text
from termcade.ui.work import work
from textual.app import ComposeResult
from textual.content import ContentText
from textual.widgets import Footer, Header, Static

from termcade.ui.widgets import BoxedPanel, TooltipStatic

from ...logic.flow.duel import COMMITMENT, END, SETUP, Amend, AmendOptions, Duel, DuelChoices, DuelState
from ...logic.schema.constants import ELEMENTS, TOURNAMENT
from ...logic.schema.models import Card
from ...logic.config.settings import XiaolinSettings
from ...logic.schema.state import XiaolinState
from ...logic.flow.turn import bot_turn, max_hand_size, refill_hands, shelve
from ..base import XiaolinScreen
from ..display.duel_board import _board_text, _showdown_story, _wager_label
from ..display.headline import SHOWDOWN_LOG, opponent_move
from ..reference.rules import RulesScreen
from ..display.format import card_options, display_name, element_text


class DuelScreen(XiaolinScreen):
    """One showdown, stepped through a phase at a time — the player presses Continue to advance,
    seeing each phase resolve, and the choice phases raise their modal inline."""

    # Rules stays bound for the whole showdown, unlike Retreat — it costs no turn and changes no state.
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

    def page_back(self) -> None:
        """Back here means Retreat, not "pop the screen".

        A duel *replaces* the temple (`switch_screen`), so popping it would land on the main menu
        instead. Retreat walks back to the temple, and refuses once the showdown is committed.
        """
        self.action_retreat()

    def action_continue(self) -> None:
        self._continue.set()

    def action_rules(self) -> None:
        """Put the rulebook on screen. The showdown underneath is mid-await on ``_continue`` and
        keeps waiting; nothing advances or is skipped. Dead while a choice modal is up, since the
        modal owns input while it is the active screen."""
        self.app.push_screen(RulesScreen())

    def action_retreat(self) -> None:
        """Back out before the showdown begins — return to the temple.

        Only available before the showdown is committed (see `_committed`).
        """
        if self._committed:
            # Not logged: a refusal isn't something that happened in the run.
            self.engine_app.notify("Gong Yi Tanpai! There is no retreat from a showdown.", log=False)
            return
        self._retreating = True
        self._continue.set()

    async def _await_continue(self, prompt: str, *, retreat: str = "") -> None:
        # The prompt line doubles as the click target (Enter/Space have no touch equivalent).
        #
        # ``retreat`` gets its own span rather than the whole line — styling the whole line once
        # made "Esc Retreat" trigger continue instead of retreat.
        line = Text(f"▶  {prompt}")
        line.stylize(Style(meta={"@click": "screen.continue()"}))
        if retreat:
            start = len(line.plain) + 8
            line.append(" " * 8)
            line.append(retreat, style=Style(meta={"@click": "screen.retreat()"}))
            # The gap belongs to neither action: a tap that lands between them should do nothing.
            line.stylize(Style(meta={}), start - 8, start)
        self.query_one("#duel-prompt", Static).update(line)
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
        """Announce the wager the opponent set."""
        name = display_name(state.bot.character.name)
        self.engine_app.notify(
            # Not logged: the showdown's own story tells who staked what, in the order it happened.
            f"{name} requested a {_wager_label(duel.wager)}",
            title="The stakes",
            log=False,
        )

    def _announce_jack_steal(self, duel: DuelState) -> None:
        """Announce Jack's card steal, immediately, before the player chooses a Wu."""
        self.engine_app.notify(
            f"Jack Spicer stole your {duel.jack_stolen} before you could field it!",
            title="AI Jack",
            log=False,
        )

    def _announce_yoyo_flip(self) -> None:
        """Announce a Yin/Yang Yo-Yo flip of the player's affiliation."""
        self.engine_app.notify(
            "It's hard to spot the difference, isn't it?",
            title="Yin-Yang Yo-Yo",
            log=False,
        )

    def _announce_end_surprises(self, duel: DuelState) -> None:
        """Two outcomes the board shows without explaining, so only a toast can account for them."""
        if duel.prize_gifted:
            # Toast only: the board's last line already carries this.
            self.engine_app.notify(
                "He beat you for the Wu, then pressed it into your hands.",
                title="The Good Guys Finish Last",
                log=False,
            )
        if any(r.player.element_cancelled or r.bot.element_cancelled for r in duel.rounds):
            # Toast only: the board doesn't otherwise explain why the elements cancelled.
            self.engine_app.notify(
                "Two Wu clashed over the element — both cancelled; each side kept its own.",
                title="Elements cancelled",
                log=False,
            )

    @work
    async def _run_showdown(self) -> None:
        state, settings, rng = self.state, self.rules, self.ctx.rng

        duel = Duel(state, rng, self._choices(), settings)
        self._duel = duel

        # Last moment to retreat — this press commits to the shown priority (or draws the coin on a tie).
        self._show_board(duel)
        await self._await_continue("Continue to begin the showdown", retreat="Esc Retreat")
        if self._retreating:
            self._retreat_to_temple()
            return
        self._committed = True
        # Past this point there is no walking away, so the way back stops being offered.
        self.hide_back()

        while True:
            stage = await duel.advance()  # one phase; a choice phase raises its modal inline
            self._show_board(duel)
            tied = duel.duel.player.initiative == duel.duel.bot.initiative
            if stage == COMMITMENT and duel.duel.jack_stolen:
                self._announce_jack_steal(duel.duel)
            # Checked every pass and cleared right away, unlike `jack_stolen`'s one-time
            # COMMITMENT-only window.
            if duel.duel.yoyo_flipped_announce:
                self._announce_yoyo_flip()
                duel.duel.yoyo_flipped_announce = False
            if stage == COMMITMENT and (tied or self.state.initiative_contested):
                await self._reveal_coin_toss(duel.duel.player_priority is True)
            # Only when a stat was called — a tournament prices itself, so there's nothing to announce.
            if stage == SETUP and duel.duel.player_priority and duel.duel.challenge != TOURNAMENT:
                self._announce_wager(duel.duel, state)
            if stage == END:  # the END stage has already run
                self._announce_end_surprises(duel.duel)
                break
            await self._await_continue("Continue")

        # Not toasted (the board already shows the result); logged as the last line of the turn.
        self.ctx.journal.add(
            _showdown_story(duel.duel, state, wear_limit=self.rules.wear_limit), title=SHOWDOWN_LOG
        )

        # No extra Continue — head straight into the temple turn once the result is on screen.
        # Skipped once the draw pile (and so the run) is spent.
        if not state.has_ended:
            await self._discard_surplus(state, settings)
            # next_turn() here, not after: what follows is the bot's half of the *next* turn opening.
            self.ctx.journal.next_turn()
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
            if len(state.player.whole_hand) <= max_hand_size(state.player, settings.max_hand_size_player):
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
            amend=self._pick_amend,
            counter=self._pick_counter,
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
        """Choose how many Wu to wager. Never asked on a tournament — there's only one to choose."""
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
        """Which stat an effect targets."""
        return await self.choose("Which stat do you name?", _stat_options(options), title="NAME A STAT")

    async def _pick_boost(self, cards: list[Card]) -> Card | None:
        options: list[tuple[ContentText, Card | None]] = [
            *card_options(cards, suffix_stats=True),
            ("Don't play", None),
        ]
        return await self.choose("Play a boost Wu?", options, title="BOOST")

    async def _pick_counter(self, cards: list[Card]) -> Card | None:
        """Field an extra Wu (off the wager, so it can't be lost) to answer a summon, or pass."""
        if self._duel is not None:
            self._show_board(self._duel)
        options: list[tuple[ContentText, Card | None]] = [
            *card_options(cards, suffix_stats=True),
            ("Pass", None),
        ]
        return await self.choose(
            "Their Heart of Jong summoned a fighter. Field an extra Wu to answer? (free — it can't be lost)",
            options,
            title="ANSWER THE SUMMON",
        )

    async def _pick_card(self, cards: list[Card]) -> Card:
        """Field a Wu. Blind — the opponent is choosing theirs at the same time."""
        if self._duel is not None:
            self._show_board(self._duel)
        return await self.choose("Play a card", card_options(cards, suffix_stats=True), title="CARD")

    async def _pick_amend(self, options: AmendOptions) -> Amend | None:
        """Rewrite one term of the round, or leave it, via a two-step picker: which term, then its
        new value."""
        kinds: list[tuple[str, str]] = []
        if options.stats:
            kinds.append(("Contest a different stat", "challenge"))
        if options.elements:
            kinds.append(("Change the arena element", "background"))
        if options.can_take_ground:
            kinds.append(("Take the challenger's ground", "initiative"))
        if options.wagers:
            kinds.append(("Raise the wager", "wager"))
        if options.swap_out and options.swap_in:
            kinds.append(("Swap a fielded Wu", "swap"))
        kinds.append(("Change nothing", ""))

        kind = await self.choose("Hodoku Mouse —  fix one thing.", kinds, title="AMEND")
        if not kind:
            return None
        if kind == "initiative":
            return Amend("initiative")
        if kind == "challenge":
            return Amend("challenge", await self.choose(
                "Contest which stat instead?", _stat_options(options.stats), title="AMEND"))
        if kind == "background":
            return Amend("background", await self.choose(
                "Which arena element instead?", _element_options(options.elements), title="AMEND"))
        if kind == "wager":
            return Amend("wager", await self.choose(
                "Raise the wager to how many Wu?",
                [(_wager_label(n), str(n)) for n in options.wagers], title="AMEND"))
        out = await self.choose(
            "Pull which fielded Wu back to hand?",
            card_options(options.swap_out, suffix_stats=True), title="AMEND")
        into = await self.choose(
            "Field which Wu in its place?",
            card_options(options.swap_in, suffix_stats=True), title="AMEND")
        return Amend("swap", swap_out=out, swap_in=into)


def _stat_options(values: list[str]) -> list[tuple[str, str]]:
    return [(value.upper(), value) for value in values]


def _element_options(values: list[str]) -> list[tuple[Text, str]]:
    """An element names itself in its own colour, on a button as on the board."""
    return [(_upper(element_text(value)), value) for value in values]


def _upper(text: Text) -> Text:
    upper = Text(text.plain.upper(), style=text.style)
    upper.spans = list(text.spans)
    return upper
