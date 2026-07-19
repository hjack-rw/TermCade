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

from rich.align import Align
from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.style import Style
from rich.table import Table
from rich.text import Text
from termcade.ui.work import work
from textual.app import ComposeResult
from textual.content import ContentText
from textual.widgets import Footer, Header, Static

from termcade.ui.widgets import BoxedPanel, TooltipStatic

from ..logic.battle import Round, Side
from ..logic.duel import BEAST_BOOST, COMMITMENT, END, SETUP, Duel, DuelChoices, DuelState
from ..logic.constants import ELEMENTS, TOURNAMENT, TOURNAMENT_BATTLES
from ..logic.mechanics.cards import is_one_of
from ..logic.models import Card, Player
from ..logic.settings import XiaolinSettings
from ..logic.state import XiaolinState
from ..logic.turn import bot_turn, max_hand_size, refill_hands, shelve
from ..logic.wear import WEAR_LIMIT
from ..logic.mechanics.powers import is_boost_slot
from ..logic.mechanics.scoring import contributing, element_score
from .base import XiaolinScreen
from .rules import RulesScreen
from .format import (
    COLORS,
    CONTESTED_STYLE,
    SHOWDOWN_LOG,
    STAT_ORDER,
    opponent_move,
    absent_stats_text,
    stat_str,
    card_label,
    card_headline,
    card_name_text,
    labelled,
    card_stats_text,
    display_name,
    element_text,
    stats_line,
    stats_text,
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
                _card_options(state.player.hand),
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
        options: list[tuple[ContentText, Card | None]] = [*_card_options(cards), ("Don't play", None)]
        return await self.choose("Play a boost Wu?", options, title="BOOST")

    async def _pick_card(self, cards: list[Card]) -> Card:
        """Field a Wu, blind. Your opponent is choosing theirs against the same board you see."""
        if self._duel is not None:
            self._show_board(self._duel)
        return await self.choose("Play a card", _card_options(cards), title="CARD")


def _wager_label(wager: int) -> str:
    """``2 vs 2`` — spaced, or the glyphs read as one token. Board, toast and log all print it."""
    return f"{wager} vs {wager}"


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




_DIVIDER_MIN = 36  # the rule under the prize never shrinks below this, however short the line is


def _board_text(duel: DuelState, state: XiaolinState) -> RenderableType:
    # The exchange on the table. Before the first Boost there is none, so an empty stand-in keeps the
    # board a pure function of the state rather than a special case at every line.
    live = duel.rounds[-1] if duel.rounds else Round()

    prize_line = _prize_line(duel)

    # The prize is not in play. A drawn rule sets it apart from the cards that are — an underline would
    # only span the glyphs and collapse to nothing when the prize is a dash.
    #
    # It is drawn to the LINE it sits under, not to a fixed width: the moment a claim was appended
    # ("[Claimed: by being in tune with the arena]") the line outgrew a 36-column rule and the rule read as
    # broken. A rule that does not reach the end of what it underlines is worse than none.
    divider = Text(
        "─" * max(_DIVIDER_MIN, prize_line.cell_len), style="dim", justify="center"
    )

    meta = Table.grid(padding=(0, 8))  # initiative / challenge / background, grouped, not spread
    meta.add_column(justify="left")
    meta.add_column(justify="center")
    meta.add_column(justify="right")
    meta.add_row(
        labelled("Challenge", (duel.challenge or "—").upper(), strong=bool(duel.challenge)),
        labelled(
            "Background",
            # The place, not the element — but coloured by the element, which is what scores. A place
            # can serve two pools, so the same name may read green today and red tomorrow.
            (duel.background_name or duel.background or "—").upper(),
            strong=bool(duel.background),
            style=COLORS.get(duel.background or "", ""),
        ),
        labelled("Initiative", f"P1: {duel.player.initiative}  P2: {duel.bot.initiative}"),
    )

    # A tournament runs three battles and needs its running score. A wagered stat challenge runs one
    # battle and needs no tally — only a reminder of how wide it is. A plain 1v1 needs neither.
    tally: list[RenderableType] = []
    if duel.challenge == TOURNAMENT:
        won_player, won_bot = duel.rounds_won
        line = Text(justify="center")
        line.append(f"Battle {max(1, duel.round_number)} of {TOURNAMENT_BATTLES}", style="bold")
        if live.stat:  # no battle on the table yet — an empty "()" would be worse than nothing
            line.append(f" ({live.stat.upper()})", style="bold")
        line.append("      ")
        line.append("Battles won: ", style="dim")
        line.append(f"P1: {won_player}  P2: {won_bot}")
        tally = [line, ""]
    elif duel.wager > 1:
        line = Text(justify="center")
        line.append(_wager_label(duel.wager), style="bold")
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
            challenge=live.stat or None, background=_resonant_background(duel),
        ),
        "",  # the two duelists' blocks are three lines each; a gap keeps them from reading as one
        _side_line(
            "P2", state.bot, live.bot,
            leads=duel.player_priority is False,
            challenge=live.stat or None, background=_resonant_background(duel),
            beast=_beast_for(duel, live),
        ),
    ]
    if duel.winner_character:
        parts += ["", Text(f"{_won(duel)} WINS!", style="bold")]
    return Group(*parts)



def _resonant_background(duel: DuelState) -> str | None:
    """The background, unless a played Serpent's Tail voided the elemental bonus — then no Wu
    resonates with it, and the board must stop claiming they do."""
    return None if duel.elemental_bonus_cancelled else duel.background


def _beast_for(duel: DuelState, live: Round) -> str | None:
    """The stat Chase's Beast Form boosts on the table right now — set only in the battle that
    contests it (a tournament's other legs see the plain stats), so the board shows it once."""
    return duel.beast_stat if duel.beast_stat and live.stat == duel.beast_stat else None


def _beast_offensive(stat: str, cards: list[Card], challenge: str | None) -> _CardsLine:
    """Chase's Beast Form as the boost it is: ``Offensive: Beast Form (0/2/0) + <Wu> (-/-/-)`` — an
    element-free, uncoloured boost lifting his own Wu, which are nullified beside it (offence_negated,
    struck like an Emperor Scorpion's victim). The +2 sits on the one stat he named."""
    tag = Text()
    tag.append("     Offensive: ", style="dim")

    beast = Text()
    beast.append("Beast Form ", style="dim")  # no element colour — the beast is not a Wu
    stats = "/".join(str(BEAST_BOOST) if s == stat else "0" for s in STAT_ORDER)
    beast.append(f"({stats})", style="dim")

    entries, joiners = [beast], [Text()]
    for card in cards:  # the Wu the beast lifts — staked, but struck to nothing
        joiners.append(Text(" + ", style="dim"))
        entry = Text()
        entry.append_text(card_name_text(card))
        entry.append(" (", style="dim")
        entry.append_text(absent_stats_text(challenge))
        entry.append(")", style="dim")
        entries.append(entry)
    return _CardsLine(tag, entries, joiners)


def _side_line(
    label: str,
    player: Player,
    side: Side,
    *,
    leads: bool,
    challenge: str | None,
    background: str | None,
    beast: str | None = None,
) -> Group:
    name = display_name(player.character.name)

    header = Text()
    header.append(f"{label}: ", style="dim")
    if leads:  # holds priority: names the challenge, and breaks a tied duel
        header.append("✫ ", style=Style(bold=True, meta={"tooltip": "Challenger"}))
    header.append(name, style="bold")
    header.append(" (base ", style="dim")
    # A Sphere of Jianyu has them: the duelist themselves count for nothing this battle, and only
    # the Wu they played answer for them.
    if side.base_negated:
        header.append_text(absent_stats_text(challenge))
    else:
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
    # Chase's Beast Form rides the Offensive line like the boost it is — ``Beast Form (0/2/0) + <Wu>``
    # — his own Wu struck to -/-/- beside it. Otherwise the ordinary line: only the Wu that still move
    # a stat earn the background's bonus (see `earns_bonus` in the scorer).
    offensive = (
        _beast_offensive(beast, side.mine(), challenge)
        if beast
        else _cards_line(
            "Offensive", side.mine(), side.amplifiers, challenge, background,
            earning=side.contributors(), negated=side.offence_negated,
        )
    )
    return Group(
        header,
        offensive,
        _cards_line(
            "Defensive", contributing(side.suffered), side.amplifiers, challenge, background,
            earning=contributing(side.suffered), sign=-1, negated=side.defence_negated,
        ),
    )


class _CardsLine:
    """A row of played Wu that breaks *between* Wu and never inside one.

    A Wu is its name and the stats it scores for, and the two only mean anything together. Rich's
    wrapper breaks on any space, so it will happily leave a name at the end of one line and its
    stats at the start of the next, and indent the remainder under the label. This lays the row out
    itself: each Wu is atomic, and a row that runs long continues under the *first Wu*, not the label.
    """

    def __init__(self, label: Text, entries: list[Text], joiners: list[Text]) -> None:
        self.label = label
        self.entries = entries
        self.joiners = joiners  # joiners[i] goes before entries[i]; joiners[0] is never used

    @property
    def renderables(self) -> tuple[Text]:
        """The whole row on one line, unwrapped — what a reader (or a test) means by its content."""
        flat = self.label.copy()
        for index, entry in enumerate(self.entries):
            if index:
                flat.append_text(self.joiners[index])
            flat.append_text(entry)
        return (flat,)

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        indent = self.label.cell_len
        line = self.label.copy()
        used = indent
        for index, entry in enumerate(self.entries):
            if index:
                line.append_text(self.joiners[index])  # the separator stays on the line it ends
                used += self.joiners[index].cell_len
            if index and used + entry.cell_len > options.max_width:
                yield line
                line = Text(" " * indent)
                used = indent
            line.append_text(entry)
            used += entry.cell_len
        yield line


def _showdown_story(duel: DuelState, state: XiaolinState) -> Text:
    """The whole showdown in order, for the Game Log — the build-up says why the result was what it was,
    and the board that showed it is gone. Every line is a fact the duel already holds."""
    if duel.stakes is None:  # retreated, or the pile ran dry: no prize was ever drawn
        return Text()

    # The duelist who holds priority names the challenge; the other answers with the background and,
    # on a stat challenge, with the price.
    caller, answerer = _duelists(duel, state)

    story = Text()
    _line(story, card_headline(duel.stakes), Text(" revealed itself!"))

    if duel.challenge == TOURNAMENT:
        _line(story, Text(f"{caller} challenged {answerer} to a Tournament!"))
    elif duel.challenge:
        _line(story, Text(f"{caller} challenged {answerer} in a battle of {duel.challenge.upper()}!"))
    if duel.background:
        # The background and the price are ONE move: the duelist who did not call the challenge answers
        # with both. Two lines made them read as two turns.
        #
        # The PLACE, coloured by the element it was summoned under — which is what scores, and which no
        # lookup could recover: half the arenas serve two elements, and the same name reads green today
        # and red tomorrow. The board colours it the same way, from the same fact.
        place = display_name(duel.background_name or duel.background)
        answer = [
            Text("The background was "),
            Text(place, style=f"bold {COLORS.get(duel.background, 'white')}"),
        ]
        # A tournament is three battles of one Wu — its price is fixed by the shape of it, and there is
        # nothing left for the answerer to name. On a stat challenge they name the width of the field,
        # in the same words the toast used when they named it to your face.
        if duel.challenge != TOURNAMENT and duel.wager:
            answer.append(Text(f", and {answerer} requested a {_wager_label(duel.wager)}"))
        answer.append(Text("!"))
        _line(story, *answer)

    _line(story, *_showdown_result(duel))
    _spoils(story, duel)
    if duel.bot_trained:
        _line(
            story,
            Text(
                f"{display_name(state.bot.character.name)} completed their training: "
                f"their {duel.bot_trained} rose."
            ),
        )
    for name, was_player, paid in duel.worn_out:
        _line(
            story,
            Text(
                f"{'Your' if was_player else 'Their'} {name} wore out after {WEAR_LIMIT} showdowns: "
                f"vaulted for {paid} pt{'s' if paid != 1 else ''}."
            ),
        )
    return story


def _spoils(story: Text, duel: DuelState) -> None:
    """What changed hands — the loser's field, which is the winner's gain.

    The *wager* is not written down: by the time this is read the price is history, and a line naming
    what each side laid out only pushes the one that matters off the top. What a duelist walked away
    with is the fact a player comes back for.

    Nothing is added when nothing moved (a dead heat), because a line saying so would be a line saying
    nothing.
    """
    if duel.winner is None:
        return
    taken = duel.duelist(not duel.winner).stakes
    if not taken:
        return
    parts: list[Text] = []
    for index, card in enumerate(taken):
        if index:
            parts.append(Text(", "))
        parts.append(card_headline(card))
    plural = "Wu" if len(taken) == 1 else "Wus"
    _line(story, *parts, Text(f" {plural} transferred hands!"))


def _line(story: Text, *parts: Text) -> None:
    """Append one line of the story, newline included — except before the first."""
    if story.plain:
        story.append("\n")
    for part in parts:
        story.append_text(part)


def _duelists(duel: DuelState, state: XiaolinState) -> tuple[str, str]:
    """``(who called it, who answered)`` — by priority, which is who names the challenge."""
    player = display_name(state.player.character.name)
    bot = display_name(state.bot.character.name)
    return (player, bot) if duel.player_priority else (bot, player)


def _showdown_result(duel: DuelState) -> tuple[Text, ...]:
    """The last line of the story.

    Winning the showdown and winning the *Wu* are two different things — a duelist can take the duel
    and still see the prize lost — so this says which happened, and never implies the other.

    The prize is named, not re-introduced: its stats were printed the moment it surfaced, three lines
    up, and a second copy of the same triple tells a reader nothing.
    """
    assert duel.stakes is not None
    prize = card_name_text(duel.stakes)
    # A spaced en dash before the coloured Wu name: unlike the em dash it does not fill the cell, so a
    # single space after it survives and the log reads "the Wu – Lasso", not "the Wu —Lasso".
    if duel.winner_character is None:
        return (Text("A dead heat – "), prize, Text(" was lost!"))
    who = display_name(duel.winner_character)
    if duel.prize_route is None:
        return (Text(f"{who} won the showdown, but not the Wu – "), prize, Text(" was lost!"))
    return (Text(f"{who} won and claimed "), prize, Text(f" by {duel.prize_route.value}!"))


def _prize_line(duel: DuelState) -> Text:
    """The Wu both duelists are racing for, and — once it is settled — how it was taken.

    A Wu that simply appears in a hand teaches a player nothing about the four ways to earn one, and
    *lost* is the outcome they will meet most often. So the board says which it was.
    """
    line = Text(justify="center")
    line.append("Prize: ", style="dim")
    if duel.stakes is None:
        line.append("? ? ?", style="dim")  # not drawn yet — spaced, as the hidden power reads
        return line

    line.append_text(card_headline(duel.stakes))
    if duel.winner is None:  # still being fought over
        return line
    # The reason is set apart on purpose. Run it straight on from the Wu's name and a reader joins the
    # two — "Serpent's Tail ... in tune with the arena" reads as a claim ABOUT the Tail, which is the
    # one Wu that could never make it. The prize is what was *won*; the route is how the winner won it.
    if duel.prize_route is None:
        line.append("   [Wu was lost, but it may surface again...]", style="dim italic")
    else:
        line.append(f"   [Claimed: by {duel.prize_route.value}]", style="dim italic")
    return line


def _cards_line(
    label: str,
    cards: list[Card],
    amplifiers: list[Card],
    challenge: str | None,
    background: str | None,
    *,
    earning: list[Card] | None = None,
    sign: int = 1,
    negated: bool = False,
) -> _CardsLine:
    """One line of the board. ``negated`` means a Sphere, Scorpion or Mirror has taken it for this
    battle: the Wu are still named — you must see what was turned off — but they read ``-/-/-`` and
    take no elemental colour, because they are not there to resonate with anything."""
    # The label's dim MUST be a span, never the Text's base style: `_CardsLine` appends the Wu into a
    # COPY of this label, and a base style would dim everything appended after it.
    tag = Text()
    tag.append(f"     {label}: ", style="dim")
    if not cards:
        return _CardsLine(tag, [Text("—")], [Text()])

    entries: list[Text] = []
    joiners: list[Text] = []
    for index, card in enumerate(cards):
        # a booster and the Wu it lifts are one play: "Bracelet + Fist", not two entries
        joined = _from_the_boost_slot(cards[index - 1], amplifiers) if index else False
        joiners.append(Text(" + " if joined else ", ", style="dim"))

        # A Wu that no longer moves a stat earns no elemental bonus, so it must not be drawn one.
        earns = not negated and (earning is None or is_one_of(card, earning))
        # A FRESH Text, and the name appended into it — `card_name_text` carries the element colour as
        # its *base* style, so building on it directly tints everything that follows. That is why the
        # stats were coming out blue on a water Wu, and why bold on top of a colour never read as
        # "brighter". `card_label` documents the same trap.
        entry = Text()
        entry.append_text(card_name_text(card))
        entry.append(" (", style="dim")
        if negated:
            entry.append_text(absent_stats_text(challenge))
        else:
            entry.append_text(
                _played_stats_text(card, challenge, background if earns else None, sign)
            )
        entry.append(")", style="dim")
        entries.append(entry)
    return _CardsLine(tag, entries, joiners)


def _played_stats_text(
    card: Card, challenge: str | None, background: str | None, sign: int = 1
) -> Text:
    """The stats as they will SCORE: the elemental shift is invisible in the printed triple, so a Wu
    could read ``0/0/4`` and score 3. Where it bites, the printed value is struck and the effective one
    follows. ``sign`` is -1 on the Defensive line — a resonant curse harms you more.
    """
    text = Text()
    shift = sign * _elemental_shift(card, challenge, background)
    for index, stat in enumerate(STAT_ORDER):
        if index:
            text.append("/", style="dim")
        value = card.stats[stat]
        # Contested stat in an explicit BRIGHT colour: bold alone is advisory and vanishes on a dim or
        # element-coloured ground.
        style = "dim" if challenge and stat != challenge else CONTESTED_STYLE
        if stat != challenge or not shift or value is None:
            text.append(stat_str(value), style=style)
            continue
        # No cell can be spared for a gap, so the two numbers part by HEIGHT: printed value struck,
        # effective value subscripted behind U+231E (whose upright stops at subscript height).
        text.append(str(value), style="dim strike")
        text.append("⌞", style="dim")
        text.append(_subscript(value + shift), style=style)
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


