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

from ...logic.characters import jack, jong
from ...logic.characters.hannibal import DEFLECTED_ELEMENTS
from ...logic.flow.battle import Round, Side
from ...logic.schema.constants import BRAWL, TOURNAMENT, TOURNAMENT_BATTLES
from ...logic.flow.duel import (
    BEAST_BOOST,
    BOOST,
    CARD,
    COMMITMENT,
    END,
    RESOLVEMENT,
    SETUP,
    DuelState,
)
from ...logic.mechanics.cards import is_one_of
from ...logic.mechanics.powers import Mechanic, is_boost_slot, mechanic_of
from ...logic.mechanics.scoring import contributing, element_score
from ...logic.schema.models import Card, Player
from ...logic.schema.state import XiaolinState
from ...logic.flow.wear import WEAR_LIMIT
from .format import (
    COLORS,
    CONTESTED_STYLE,
    STAT_ORDER,
    absent_stats_text,
    card_name_text,
    card_stats_text,
    display_name,
    labelled,
    stat_str,
    stats_text,
)
from .headline import card_headline


def _wager_label(wager: int) -> str:
    """``2 vs 2`` — spaced, or the glyphs read as one token. Board, toast and log all print it."""
    return f"{wager} vs {wager}"


# Keyed by the stage machine's own constants (imported from `duel`), never by bare integers — a
# literal `{0: "End", 1: ...}` would silently go stale if the stages were reordered.
# SETUP is absent on purpose — it has two names depending on who moved, handled below.
_PHASE_NAMES = {
    END: "End",
    COMMITMENT: "Commitment",
    BOOST: "Boost",
    CARD: "Card",
    RESOLVEMENT: "Resolvement",
}


def _phase_name(duel: DuelState) -> str:
    # END is reused: the fresh pre-showdown board (no winner yet) vs the closing end phase.
    if duel.stage == END and duel.winner_character is None:
        return "Gong Yi Tanpai!"
    if duel.stage == SETUP:
        # One stage, two possible titles: the priority holder names the stat ("Challenge"), the
        # other answers with the element ("Background").
        return "Challenge" if duel.player_priority else "Background"
    return _PHASE_NAMES.get(duel.stage, "")


def _won(duel: DuelState) -> str:
    return display_name(duel.winner_character or "", upper=True)




_DIVIDER_MIN = 36  # the rule under the prize never shrinks below this, however short the line is


def _board_text(duel: DuelState, state: XiaolinState) -> RenderableType:
    # Empty stand-in before the first Boost, so the board stays a pure function of state rather than
    # a special case at every line.
    live = duel.rounds[-1] if duel.rounds else Round()

    # Hannibal's Elemental Deflection: the scorer turns aside the elements (metal aside), so the board
    # must not strike a shift it never took. The opponent is always P2 (the bot).
    _bot_deflects = state.bot.character.name == "Hannibal_Roy_Bean"

    prize_line = _prize_line(duel)

    # Sized to the LINE it sits under, not a fixed width — a fixed 36-column rule went visibly short
    # once a "[Claimed: ...]" suffix could be appended to the prize line.
    divider = Text(
        "─" * max(_DIVIDER_MIN, prize_line.cell_len), style="dim", justify="center"
    )

    # Brawl's meta row reads "Element" instead of "Challenge"/"Background" — it has no named stat or
    # place, so the normal labels would misread as a background that just never changed.
    is_brawl = duel.challenge == BRAWL
    meta = Table.grid(padding=(0, 8))  # initiative / challenge / background, grouped, not spread
    meta.add_column(justify="left")
    meta.add_column(justify="center")
    meta.add_column(justify="right")
    meta.add_row(
        labelled(
            "Challenge", "BRAWL!" if is_brawl else (duel.challenge or "—").upper(),
            strong=bool(duel.challenge),
        ),
        labelled(
            "Element" if is_brawl else "Background",
            # Coloured by the element as summoned, not looked up — a place can serve more than one
            # element pool, so the same name may read a different colour next time.
            (duel.background or "—").upper() if is_brawl
            else (duel.background_name or duel.background or "—").upper(),
            strong=bool(duel.background),
            style=COLORS.get(duel.background or "", ""),
        ),
        labelled("Initiative", f"P1: {duel.player.initiative}  P2: {duel.bot.initiative}"),
    )

    # Tournament shows a running score; a wagered challenge shows just the wager width; a plain 1v1
    # shows neither.
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
    elif is_brawl:
        # Both wagers shown — a single "wager" would imply the one shared number every other
        # showdown has, but a brawl's two sides needn't match.
        line = Text(justify="center")
        line.append(f"P1 wagers: {duel.player_wager or 0}   P2 wagers: {duel.bot_wager or 0}", style="bold")
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
            # Against Hannibal the player's elemental lift is turned aside — the board must not strike it.
            deflect="lift" if _bot_deflects else None,
        ),
        "",  # the two duelists' blocks are three lines each; a gap keeps them from reading as one
        _side_line(
            "P2", state.bot, live.bot,
            leads=duel.player_priority is False,
            challenge=live.stat or None, background=_resonant_background(duel),
            beast=_beast_for(duel, live),
            # Hannibal himself: his own Wu shrug off the arena's drag, so no strike either.
            deflect="ward" if _bot_deflects else None,
            # `jack_mode` is the shown name for AI Jack / Chamelon-Bot; Attack! rotates through
            # `attack_bot_name` instead — see `DuelState.jack_mode`. Attack! and Good Jack's headers
            # read what they actually score as (`shown_stats`), not the printed base stats.
            shown_name=duel.attack_bot_name if duel.jack_mode == jack.ATTACK_NAME else duel.jack_mode,
            shown_stats=_jack_stats(duel, state.bot, state.player),
        ),
    ]
    if duel.winner_character:
        parts += ["", Text(f"{_won(duel)} WINS!", style="bold")]
    return Group(*parts)



def _resonant_background(duel: DuelState) -> str | None:
    """The background, unless the elemental bonus was cancelled this battle — then no Wu resonates
    with it, and the board must stop claiming they do."""
    return None if duel.elemental_bonus_cancelled else duel.background


def _beast_for(duel: DuelState, live: Round) -> str | None:
    """The stat Beast Form boosts on the table right now — set only in the battle that contests it,
    so the board shows it once."""
    return duel.beast_stat if duel.beast_stat and live.stat == duel.beast_stat else None


def _jack_stats(
    duel: DuelState, jack_player: Player, opponent: Player
) -> dict[str, int] | None:
    """His shown stats when they diverge from his own printed base, mirroring `duel.Duel._jack_base`.
    ``None`` for AI Jack, plain Jack, or Chamelon-Bot — Chamelon-Bot's denial is a boost, already on
    the Offensive line, so baking it into the header too would double-count it. Attack! is flat
    ATTACK_STAT plus the same metal resonance swing `_jack_base` applies; Good Jack is GOOD_JACK_STAT
    on force/agility plus his separately trained intellect. Duplicated here rather than shared with
    `duel.py` (same as `_beast_for`): this module only ever reads `DuelState`, never a live `Duel`.
    """
    if duel.jack_mode == jack.ATTACK_NAME:
        swing = element_score("metal", duel.background) if duel.background else 0
        return {stat: jack.ATTACK_STAT + swing for stat in jong.battle_stats(opponent)}
    if mechanic_of(jack_player.character.power) is Mechanic.BOT and jack_player.yoyo_flipped:
        real = jack_player.character.stats
        return {
            "force": jack.GOOD_JACK_STAT + (real["force"] - jack.JACK_PRINTED_PHYSICAL),
            "agility": jack.GOOD_JACK_STAT + (real["agility"] - jack.JACK_PRINTED_PHYSICAL),
            "intellect": jack_player.good_jack_intellect,
        }
    return None


def _beast_offensive(stat: str, cards: list[Card], challenge: str | None) -> _CardsLine:
    """Beast Form as the boost it is: ``Offensive: Beast Form (0/1/0) + <Wu> (-/-/-)`` — an
    element-free, uncoloured boost lifting his own Wu, which are struck to nothing beside it
    (offence_negated). BEAST_BOOST sits on the one stat he named."""
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
    deflect: str | None = None,
    shown_name: str | None = None,
    shown_stats: dict[str, int] | None = None,
) -> Group:
    name = display_name(shown_name or jong.shown_name(player))

    header = Text()
    header.append(f"{label}: ", style="dim")
    if leads:  # holds priority: names the challenge, and breaks a tied duel
        header.append("✫ ", style=Style(bold=True, meta={"tooltip": "Challenger"}))
    header.append(name, style="bold")
    header.append(" (base ", style="dim")
    # base_negated: the duelist's own stats count nothing this battle, only the Wu they played.
    if side.base_negated:
        header.append_text(absent_stats_text(challenge))
    else:
        header.append_text(card_stats_text(shown_stats or jong.battle_stats(player), challenge))
    header.append(")", style="dim")
    if side.result:  # score appears once scoring has run; joined to its arrow so they wrap as one unit
        header.append("   ")
        header.append("→  ", style="dim")
        header.append_text(stats_text([str(value) for value in side.result], challenge))

    # `side.mine()`/`side.suffered` already distinguish played Wu from curses cast at this duelist —
    # don't re-derive that split here. Both lines always render (a dash, not a missing line) so the
    # two duelists' blocks stay the same height. Background applies in opposite directions per line —
    # lift on Offensive, drag on Defensive — so the printed shifts sum to the total by `base`.
    offensive = (
        _beast_offensive(beast, side.mine(), challenge)
        if beast
        else _cards_line(
            "Offensive", side.mine(), side.amplifiers, challenge, background,
            earning=side.contributors(), negated=side.offence_negated, deflect=deflect,
        )
    )
    return Group(
        header,
        offensive,
        _cards_line(
            "Defensive", contributing(side.suffered), side.amplifiers, challenge, background,
            earning=contributing(side.suffered), sign=-1, negated=side.defence_negated,
            jack_bot=side.jack_bot,
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
    """The whole showdown in order, for the Game Log. Every line is a fact the duel already holds."""
    if duel.stakes is None:  # retreated, or the pile ran dry: no prize was ever drawn
        return Text()

    # The duelist who holds priority names the challenge; the other answers.
    caller, answerer = _duelists(duel, state)

    story = Text()
    _line(story, card_headline(duel.stakes), Text(" revealed itself!"))

    if duel.challenge == TOURNAMENT:
        _line(story, Text(f"{caller} challenged {answerer} to a Tournament!"))
    elif duel.challenge:
        _line(story, Text(f"{caller} challenged {answerer} in a battle of {duel.challenge.upper()}!"))
    if duel.background:
        # Coloured by the element as summoned, not looked up — same reasoning as the board's own
        # background label.
        place = display_name(duel.background_name or duel.background)
        answer = [
            Text("The background was "),
            Text(place, style=f"bold {COLORS.get(duel.background, 'white')}"),
        ]
        # Tournament's price is fixed by its shape; only a stat challenge has a wager to report.
        if duel.challenge != TOURNAMENT and duel.wager:
            answer.append(Text(f", and {answerer} requested a {_wager_label(duel.wager)}"))
        answer.append(Text("!"))
        _line(story, *answer)

    _line(story, *_showdown_result(duel))
    if duel.jack_stolen:
        _line(
            story,
            Text(f"{display_name(state.bot.character.name)} stole {duel.jack_stolen}!"),
        )
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
    """What changed hands: the loser's staked field, taken by the winner. Nothing is added on a
    dead heat, when nothing moved."""
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
    """The last line of the story: winning the showdown and winning the *Wu* are two different
    things, so this says which happened and never implies the other. The prize is named without its
    stats — already printed three lines up."""
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
        # Said outright: the prize just turns up in the other duelist's hand, invisibly, so the line
        # must say so or it reads as the winner keeping it.
        return (
            Text(f"{who} won and claimed "),
            prize,
            Text(f" by {duel.prize_route.value} – then handed it to you!"),
        )
    return (Text(f"{who} won and claimed "), prize, Text(f" by {duel.prize_route.value}!"))


def _prize_line(duel: DuelState) -> Text:
    """The Wu both duelists are racing for, and — once it is settled — how it was taken."""
    line = Text(justify="center")
    line.append("Prize: ", style="dim")
    if duel.stakes is None:
        line.append("? ? ?", style="dim")  # not drawn yet — spaced, as the hidden power reads
        return line

    line.append_text(card_headline(duel.stakes))
    if duel.winner is None:  # still being fought over
        return line
    # Set apart, not run on from the Wu's name — run together it reads as a claim about the Wu itself
    # rather than about how it was won.
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
    deflect: str | None = None,
    jack_bot: list[Card] | None = None,
) -> _CardsLine:
    """One line of the board. ``negated`` means a nullifying effect has taken it for this battle: the
    Wu are still named, but read ``-/-/-`` and take no elemental colour."""
    # The label's dim MUST be a span, never the Text's base style: `_CardsLine` appends the Wu into a
    # COPY of this label, and a base style would dim everything appended after it.
    tag = Text()
    tag.append(f"     {label}: ", style="dim")
    if not cards:
        return _CardsLine(tag, [Text("—")], [Text()])

    entries: list[Text] = []
    joiners: list[Text] = []
    for index, card in enumerate(cards):
        # A booster and the Wu it lifts are one play: "X + Y", not two entries. An ANIMATE summon or
        # a jack_bot entry is a separate construct, not stats blended in, so it joins with " & " instead.
        prev = cards[index - 1] if index else None
        if prev is not None and _from_the_boost_slot(prev, amplifiers, jack_bot):
            is_construct = mechanic_of(prev.power) is Mechanic.ANIMATE or is_one_of(prev, jack_bot or ())
            joiner = " & " if is_construct else " + "
        else:
            joiner = ", "
        joiners.append(Text(joiner, style="dim"))

        # A Wu that no longer moves a stat earns no elemental bonus, so it must not be drawn one.
        earns = not negated and (earning is None or is_one_of(card, earning))
        # Fresh Text: `card_name_text` carries the element colour as its *base* style, so building on
        # it directly would tint everything appended after it (see `card_label`).
        entry = Text()
        entry.append_text(card_name_text(card))
        entry.append(" (", style="dim")
        if negated:
            entry.append_text(absent_stats_text(challenge))
        else:
            entry.append_text(
                _played_stats_text(card, challenge, background if earns else None, sign, deflect)
            )
        entry.append(")", style="dim")
        entries.append(entry)
    return _CardsLine(tag, entries, joiners)


def _played_stats_text(
    card: Card, challenge: str | None, background: str | None, sign: int = 1,
    deflect: str | None = None,
) -> Text:
    """The stats as they will SCORE, not as printed: where the elemental shift bites, the printed
    value is struck and the effective one follows. ``sign`` is -1 on the Defensive line.

    ``deflect`` mirrors Elemental Deflection in the scorer: ``"ward"`` cancels a negative shift,
    ``"lift"`` a positive one, both only on ``DEFLECTED_ELEMENTS``. Without it the strike would claim
    a shift the score never took.
    """
    text = Text()
    shift = sign * _elemental_shift(card, challenge, background)
    if deflect and card.element in DEFLECTED_ELEMENTS:
        if (deflect == "ward" and shift < 0) or (deflect == "lift" and shift > 0):
            shift = 0
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


def _from_the_boost_slot(card: Card, amplifiers: list[Card], jack_bot: list[Card] | None = None) -> bool:
    """Was ``card`` played at the power stage, ahead of the card the board prints next to it?

    Three boost mechanics qualify: the dragon, the amplifier, and Jack-Bot's curse. A mirror strips
    the power off the card it negates, so identity — tracked via ``amplifiers``/``jack_bot`` — is the
    only way left to tell which slot a card was played from.
    """
    return is_one_of(card, amplifiers) or is_one_of(card, jack_bot or ()) or is_boost_slot(card.power)
