"""Duel screen — one showdown, driven by the async :class:`~..logic.duel.Duel` stage machine.

The stage machine awaits the player's decisions; here each ``await`` raises a :class:`ChoiceModal`
via ``push_screen_wait`` and resolves with the chosen value. The whole showdown runs in an async
worker so the UI stays responsive and the pure game logic never touches Textual.

One press of "Gong Yi Tanpai" plays exactly one showdown (stages 1→6→0). The vault turn runs here
too, at the end — you shelve any surplus Wu, the bot takes its turn, and the hands settle — so
control returns to the vault, or, when the draw pile is spent, to the :class:`~.outcome.OutcomeScreen`.
"""

from __future__ import annotations

import asyncio
from typing import cast

from rich.align import Align
from rich.console import Group, RenderableType
from rich.style import Style
from rich.table import Table
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.content import ContentText
from textual.widgets import Footer, Header, Static

from termcade.ui.screens.base import EngineScreen
from termcade.ui.widgets import BoxedPanel, TooltipStatic

from ..logic.duel import COMMITMENT, END, SETUP, Duel, DuelChoices, DuelState, Round, Side
from ..logic.constants import ELEMENTS
from ..logic.mechanics.cards import is_one_of
from ..logic.models import Card, Player
from ..logic.settings import XiaolinSettings
from ..logic.state import XiaolinState
from ..logic.turn import bot_turn, max_hand_size, refill_hands
from ..logic.mechanics.powers import is_boost_slot
from ..logic.mechanics.scoring import contributing, element_score
from .format import (
    COLORS,
    STAT_ORDER,
    stat_str,
    card_label,
    card_name_text,
    card_stats_text,
    display_name,
    element_text,
    stats_line,
    stats_text,
)


class DuelScreen(EngineScreen):
    """One showdown, stepped through a phase at a time — the player presses Continue to advance,
    seeing each phase resolve, and the choice phases raise their modal inline."""

    BINDINGS = [
        ("enter,space", "continue", "Continue"),
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

    def action_retreat(self) -> None:
        """Back out before the showdown begins — return to the vault.

        Only the opening board offers this: from the first "Continue" the priority is locked (or the
        coin is thrown) and the prize is drawn, so there is nothing left to walk away from.
        """
        if self._committed:
            self.app.notify("Gong Yi Tanpai! There is no retreat from a showdown.")
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

    async def _announce_wager(self, duel: DuelState, state: XiaolinState) -> None:
        """You called the challenge, so your opponent sets the price — and names it to your face.

        Only when *they* named it: a wager you chose yourself needs no announcing.
        """
        name = display_name(state.bot.character.name)
        await self.show_message(
            f"{name} answers {duel.wager} v {duel.wager}.  {_wager_terms(duel.wager)}",
            title="THE STAKES",
        )

    @work
    async def _run_showdown(self) -> None:
        state = cast(XiaolinState, self.ctx.state)
        settings = XiaolinSettings.from_settings(self.ctx.settings.current)
        rng = self.ctx.rng
        duel = Duel(state, rng, self._choices(), settings)
        self._duel = duel

        # Initiative is already on the board: this press commits you to the priority you can see, or
        # (on a tie) draws the coin that settles it. It is the last moment you may walk away.
        self._show_board(duel)
        await self._await_continue("Continue to begin the showdown        (Esc retreats)")
        if self._retreating:
            self._retreat_to_vault()
            return
        self._committed = True

        while True:
            stage = await duel.advance()  # one phase; a choice phase raises its modal inline
            self._show_board(duel)
            if stage == COMMITMENT and duel.duel.player.initiative == duel.duel.bot.initiative:
                await self._reveal_coin_toss(duel.duel.player_priority is True)
            if stage == SETUP and duel.duel.player_priority:  # they named the stakes — say so
                await self._announce_wager(duel.duel, state)
            if stage == END:  # the end phase (the loser's stakes change hands) has run
                break
            await self._await_continue("Continue")

        # The result is already on screen, so head straight into the vault turn (no extra Continue):
        # you shelve any surplus Wu (your choice), the bot banks points, then the
        # hands settle (which may flag the run over on the point limit). Skip once the pile is spent.
        if not state.has_ended:
            await self._discard_surplus(state, settings)
            difficulty = self.ctx.settings.current.difficulty  # the bot's deposit skill follows it
            self.app.notify(
                "\n".join(bot_turn(state, settings, rng=rng, difficulty=difficulty)), title="Opponent's turn"
            )
            refill_hands(state, settings, rng=rng)
        self._leave()

    async def _discard_surplus(self, state: XiaolinState, settings: XiaolinSettings) -> None:
        """Over the hand limit (you just won cards) → choose which Wu to shelve to your deck."""
        while not state.has_ended:
            if len(state.player.whole_hand) <= max_hand_size(state.player, settings.max_hand_size):
                return
            card = await self.choose(
                "Too many Wu — shelve one to your deck",
                _card_options(state.player.hand),
                title="DISPOSE",
            )
            state.player.remove_card(card)
            state.player.deck.append(card)

    def _leave(self) -> None:
        # Lazy imports: the vault imports this screen, so importing it at module load would cycle.
        if cast(XiaolinState, self.ctx.state).has_ended:
            from .outcome import OutcomeScreen

            self.app.switch_screen(OutcomeScreen())
        else:
            from .vault import VaultScreen

            self.app.switch_screen(VaultScreen())

    def _retreat_to_vault(self) -> None:
        """Abandon an uncommitted showdown — no prize drawn, no cards staked, nothing to undo."""
        from .vault import VaultScreen

        self.app.switch_screen(VaultScreen())

    def _show_board(self, duel: Duel) -> None:
        self.query_one("#duel-body", TooltipStatic).update(
            _board_text(duel.duel, cast(XiaolinState, self.ctx.state))
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
        )

    async def _pick_challenge(self, options: list[str]) -> str:
        return await self.choose("Choose the challenge stat", _stat_options(options), title="CHALLENGE")

    async def _pick_background(self, options: list[str]) -> str:
        return await self.choose("Choose the background element", _element_options(options), title="BACKGROUND")

    async def _pick_wager(self, options: list[int]) -> int:
        """They named the challenge; you name the price. Both hands are face up — read them."""
        if len(options) == 1:
            return options[0]  # nothing to decide: one of you can only field the one Wu
        return await self.choose(
            "They called the Showdown. How many Wu will you stake?",
            [(_wager_label(n), n) for n in options],
            title="THE STAKES",
        )

    async def _pick_element(self, _background: str) -> str:
        return await self.choose("Choose an element", _element_options(list(ELEMENTS)), title="ELEMENT")

    async def _pick_boost(self, cards: list[Card]) -> Card | None:
        options: list[tuple[ContentText, Card | None]] = [*_card_options(cards), ("Don't play", None)]
        return await self.choose("Play a boost Wu?", options, title="BOOST")

    async def _pick_card(self, cards: list[Card]) -> Card:
        return await self.choose("Play a card", _card_options(cards), title="CARD")


def _wager_label(wager: int) -> str:
    if wager == 1:
        return "1 Wu  —  a single exchange"
    return f"{wager} Wu  —  best of {wager}"


def _stat_options(values: list[str]) -> list[tuple[str, str]]:
    return [(value.upper(), value) for value in values]


def _element_options(values: list[str]) -> list[tuple[Text, str]]:
    """An element names itself in its own colour, on a button as on the board."""
    return [(_upper(element_text(value)), value) for value in values]


def _upper(text: Text) -> Text:
    upper = Text(text.plain.upper(), style=text.style)
    upper.spans = list(text.spans)
    return upper


def _card_options(cards: list[Card]) -> list[tuple[Text, Card]]:
    """Element-coloured button labels — a Wu reads the same on a button as on the board."""
    return [(card_label(card, f"  ({stats_line(card.stats)})"), card) for card in cards]


_SETUP_STAGE = 2  # named for what *you* do there: pick the challenge, or answer with the background

_PHASE_NAMES = {
    0: "End",
    1: "Commitment",
    3: "Boost",
    4: "Card",
    5: "Resolvement",
}


def _phase_name(duel: DuelState) -> str:
    # stage 0 is reused: the fresh pre-showdown board (no winner yet) vs the closing end phase.
    if duel.stage == 0 and duel.winner_character is None:
        return "Gong Yi Tanpai!"
    if duel.stage == _SETUP_STAGE:
        # Setup is one stage but two moves: the priority holder names the contested stat, the other
        # answers with the element. Title it with the move *this* duelist made.
        return "Challenge" if duel.player_priority else "Background"
    return _PHASE_NAMES.get(duel.stage, "")


def _won(duel: DuelState) -> str:
    return display_name(duel.winner_character or "").upper()


def _labelled(label: str, value: str, *, strong: bool = False, style: str = "") -> Text:
    """A dim label followed by its value — the muted-label / bright-value pairing used on the board.

    ``style`` tints the value; the background carries its element colour, as Wu names do.
    """
    text = Text()
    text.append(f"{label}: ", style="dim")
    text.append(value, style=f"{style} bold".strip() if strong else style)
    return text


_DIVIDER_WIDTH = 36  # a rule under the prize; deliberately short of the board's width


def _board_text(duel: DuelState, state: XiaolinState) -> RenderableType:
    # The exchange on the table. Before the first Boost there is none, so an empty stand-in keeps the
    # board a pure function of the state rather than a special case at every line.
    live = duel.rounds[-1] if duel.rounds else Round()

    prize_line = Text(justify="center")  # the prize sits on its own centred line
    prize_line.append("Prize: ", style="dim")
    if duel.stakes is None:
        prize_line.append("? ? ?", style="dim")  # not drawn yet — spaced, as the hidden power reads
    else:
        prize_line.append_text(card_name_text(duel.stakes, bold=True))
        prize_line.append(f" ({stats_line(duel.stakes.stats)})")

    # The prize is not in play. A short drawn rule sets it apart from the cards that are — an
    # underline would only span the glyphs, and collapses to nothing when the prize is a dash.
    divider = Text("─" * _DIVIDER_WIDTH, style="dim", justify="center")

    meta = Table.grid(padding=(0, 8))  # initiative / challenge / background, grouped, not spread
    meta.add_column(justify="left")
    meta.add_column(justify="center")
    meta.add_column(justify="right")
    meta.add_row(
        _labelled("Challenge", (duel.challenge or "—").upper(), strong=bool(duel.challenge)),
        _labelled(
            "Background",
            # The place, not the element — but coloured by the element, which is what scores. A place
            # can serve two pools, so the same name may read green today and red tomorrow.
            (duel.background_name or duel.background or "—").upper(),
            strong=bool(duel.background),
            style=COLORS.get(duel.background or "", ""),
        ),
        _labelled("Initiative", f"P1: {duel.player.initiative}  P2: {duel.bot.initiative}"),
    )

    # A best-of-1 has nothing to tally; anything more needs its running score on the board.
    tally: list[RenderableType] = []
    if duel.wager > 1:
        player_rounds, bot_rounds = duel.rounds_won
        line = Text(justify="center")
        line.append(f"Round {max(1, duel.round_number)} of {duel.wager}", style="bold")
        line.append("      ")
        line.append("Rounds won: ", style="dim")
        line.append(f"P1: {player_rounds}  P2: {bot_rounds}")
        tally = [line, ""]

    parts: list[RenderableType] = [
        Text(f"—  {_phase_name(duel)} —", style="bold", justify="center"),  # the em-dash eats the space to its right
        "",
        prize_line,
        divider,
        "",
        Align.center(meta),
        "",
        *tally,
        _side_line(
            "P1", state.player, live.player,
            leads=duel.player_priority is True,
            challenge=duel.challenge, background=_resonant_background(duel),
        ),
        "",  # the two duelists' blocks are three lines each; a gap keeps them from reading as one
        _side_line(
            "P2", state.bot, live.bot,
            leads=duel.player_priority is False,
            challenge=duel.challenge, background=_resonant_background(duel),
        ),
    ]
    if duel.winner_character:
        parts += ["", Text(f"{_won(duel)} WINS!", style="bold")]
    return Group(*parts)


def _wager_terms(wager: int) -> str:
    """What the stakes actually cost you, in words — the board only shows the number."""
    if wager == 1:
        return "One Wu each. The loser forfeits it."
    return f"Best of {wager} — field {wager} Wu each. The loser forfeits all {wager}."


def _resonant_background(duel: DuelState) -> str | None:
    """The background, unless a played Serpent's Tail voided the elemental bonus — then no Wu
    resonates with it, and the board must stop claiming they do."""
    return None if duel.elemental_bonus_cancelled else duel.background


def _side_line(
    label: str,
    player: Player,
    side: Side,
    *,
    leads: bool,
    challenge: str | None,
    background: str | None,
) -> Group:
    name = display_name(player.character.name)

    header = Text()
    header.append(f"{label}: ", style="dim")
    if leads:  # holds priority: names the challenge, and breaks a tied duel
        header.append("✫ ", style=Style(bold=True, meta={"tooltip": "Challenger"}))
    header.append(name, style="bold")
    header.append(" (base ", style="dim")
    header.append_text(card_stats_text(player.character.stats, challenge))
    header.append(")", style="dim")
    if side.result:  # score appears once scoring has run; joined to its arrow so they wrap as one unit
        header.append("   ")
        header.append("→  ", style="dim")
        header.append_text(stats_text([str(value) for value in side.result], challenge))

    # The queue mixes two things — Wu this duelist played and curses cast at them. `Side` already
    # knows the difference; splitting it again here is how the board and the scorer drift apart.
    # Both lines always render — a dash reads as "nothing there", where a missing line reads as a
    # bug, and the two duelists' blocks stay the same height.
    # Both lines read the background, in opposite directions: what lifts a Wu you played drags down
    # a curse cast at you. Printed here exactly as scored, so the shifts sum to the total by `base`.
    return Group(
        header,
        _cards_line("Offensive", side.contributors(), side.amplifiers, challenge, background),
        _cards_line(
            "Defensive", contributing(side.suffered), side.amplifiers, challenge, background, sign=-1
        ),
    )


def _cards_line(
    label: str,
    cards: list[Card],
    amplifiers: list[Card],
    challenge: str | None,
    background: str | None,
    *,
    sign: int = 1,
) -> Text:
    line = Text()
    line.append(f"     {label}: ", style="dim")
    if not cards:
        line.append("—")
    for index, card in enumerate(cards):
        if index:  # a booster and the Wu it lifts are one play: "Bracelet + Fist", not two entries
            line.append(" + " if _from_the_boost_slot(cards[index - 1], amplifiers) else ", ", style="dim")
        line.append_text(card_name_text(card))  # element-coloured, as in the hand panels
        line.append(" (", style="dim")
        line.append_text(_played_stats_text(card, challenge, background, sign))
        line.append(")", style="dim")
    return line


def _played_stats_text(
    card: Card, challenge: str | None, background: str | None, sign: int = 1
) -> Text:
    """The card's stats as they will score, showing the elemental bonus where it lands.

    The background lifts a resonant Wu by 1 on the contested stat and drags an opposed one down by
    1 — invisible in the printed triple, which is why a Wu could read ``0/0/4`` and score 3. Where it
    bites, the printed value is struck and the value that counts follows it: ``0/0/4 3``.

    ``sign`` is ``-1`` on the Defensive line: a curse resonating with the background harms you more,
    so its printed value drops further.
    """
    text = Text()
    shift = sign * _elemental_shift(card, challenge, background)
    for index, stat in enumerate(STAT_ORDER):
        if index:
            text.append("/", style="dim")
        value = card.stats[stat]
        style = "dim" if challenge and stat != challenge else ""
        if stat != challenge or not shift or value is None:
            text.append(stat_str(value), style=style)
            continue
        # A terminal cell is indivisible, so no gap can be *narrower* than a column. Separate the two
        # numbers vertically instead: the printed one keeps its size and is struck, the one that
        # counts drops to a subscript beneath. No column spent on a gap, and they cannot read as one
        # number.
        # No column can be spared for a gap, so the two numbers part by height: the printed one struck
        # at full size, the one that counts subscripted behind a bottom-left corner (U+231E), whose
        # upright stops at the subscript's height rather than the digit's.
        text.append(str(value), style="dim strike")  # what the card prints
        text.append("⌞", style="dim")
        text.append(_subscript(value + shift), style=style)  # what it is worth here
    return text


_SUBSCRIPT = str.maketrans("0123456789-", "₀₁₂₃₄₅₆₇₈₉₋")


def _subscript(value: int) -> str:
    return str(value).translate(_SUBSCRIPT)


def _elemental_shift(card: Card, challenge: str | None, background: str | None) -> int:
    """±1 on the contested stat, or 0 — a mirror has no element, and a voided bonus no background."""
    if not challenge or not background or not card.element:
        return 0
    return element_score(card.element, background)


def _from_the_boost_slot(card: Card, amplifiers: list[Card]) -> bool:
    """Was ``card`` played at the power stage, ahead of the card the board prints next to it?

    Both boost Wu qualify — the dragon (``boost``/0, lends a flat 1/1/1) and the amplifier
    (``boost``/+1, lends 1 per stat the next card moves). They differ in what they lend, not in
    when they land, and the ``+`` is about the slot. A mirrored amplifier is inert, its power
    stripped, so only the duel remembers what it was.
    """
    return is_one_of(card, amplifiers) or is_boost_slot(card.power)


