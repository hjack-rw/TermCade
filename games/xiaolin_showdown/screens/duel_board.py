"""Rendering the showdown board and its Game-Log story — pure functions of the duel state.

Split from :mod:`.duel`, which drives the stage machine and raises the modals; this module only turns
a :class:`~..logic.duel.DuelState` into what the player reads. Nothing here touches Textual or awaits.
"""

from __future__ import annotations

from rich.align import Align
from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.style import Style
from rich.table import Table
from rich.text import Text

from ..logic.battle import Round, Side
from ..logic.constants import TOURNAMENT, TOURNAMENT_BATTLES
from ..logic.duel import BEAST_BOOST, DuelState
from ..logic.mechanics.cards import is_one_of
from ..logic.mechanics.powers import is_boost_slot
from ..logic.mechanics.scoring import contributing, element_score
from ..logic.models import Card, Player
from ..logic.state import XiaolinState
from ..logic.wear import WEAR_LIMIT
from .format import (
    COLORS,
    CONTESTED_STYLE,
    STAT_ORDER,
    absent_stats_text,
    card_headline,
    card_name_text,
    card_stats_text,
    display_name,
    labelled,
    stat_str,
    stats_text,
)


def _wager_label(wager: int) -> str:
    """``2 vs 2`` — spaced, or the glyphs read as one token. Board, toast and log all print it."""
    return f"{wager} vs {wager}"


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
    return display_name(duel.winner_character or "", upper=True)




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
    if duel.prize_gifted:
        # He won it and gave it away. Said outright because it is the one thing here the player cannot
        # see happen: the Wu just turns up in their hand, and without this the line above would read
        # as Chase keeping a Wu they are holding.
        return (
            Text(f"{who} won and claimed "),
            prize,
            Text(f" by {duel.prize_route.value} – then handed it to you!"),
        )
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
