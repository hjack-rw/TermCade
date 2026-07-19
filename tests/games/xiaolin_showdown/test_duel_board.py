"""The duel board's rendering.

Wu names carry their element colour, as in the hand panels. Beyond that the board must keep two
things apart that the scoring queue deliberately mixes: the Wu a duelist *played*, and the curse
mirrors their opponent landed on them.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

import io

from rich.console import Console, RenderableType
from rich.text import Text

from xiaolin_showdown.logic.constants import TOURNAMENT
from xiaolin_showdown.logic.battle import Round, Side
from xiaolin_showdown.logic.duel import DuelState
from xiaolin_showdown.logic.mechanics.resolve import resolve_played_power
from xiaolin_showdown.screens.duel_board import _board_text, _cards_line
from xiaolin_showdown.screens.format import COLORS

SILVER_MANTA_RAY = 1  # water, boost/0 — a dragon, lends 1/1/1
LONGI_SASH = 3  # fire
FIST_OF_TEBIGONG = 6  # metal, play/0 — 4/0/0
WUSHU_BRACELET = 14  # boost/+1 — the booster
JU_JU_FLYTRAP = 22  # a negative Wu: 0/0/-2
SILK_SPITTER = 23  # a negative Wu — a curse, and water
TWO_TON_TUNIC = 17  # a negative Wu: -4/0/0, metal


def _texts(renderable: RenderableType) -> Iterator[Text]:
    """Every ``Text`` on the board: the ``Group`` each side line is built from, and the ``Table``
    grid that spreads initiative / challenge / background across the width."""
    if isinstance(renderable, Text):
        yield renderable
    for child in getattr(renderable, "renderables", ()):
        yield from _texts(child)
    inner = getattr(renderable, "renderable", None)  # Align wraps the meta grid
    if inner is not None:
        yield from _texts(inner)
    for column in getattr(renderable, "columns", ()):
        for cell in column.cells:
            yield from _texts(cell)


def _styles_over(board: RenderableType, needle: str) -> set[str]:
    """The styles covering ``needle`` on the board.

    Raises when the text is absent: a renamed Wu would otherwise leave an empty set, and an
    ``in`` assertion over nothing passes.
    """
    for text in _texts(board):
        start = text.plain.find(needle)
        if start == -1:
            continue
        return {str(span.style) for span in text.spans if span.start <= start < span.end}
    raise AssertionError(f"{needle!r} does not appear on the board")


def _plain(board: RenderableType) -> str:
    return "\n".join(text.plain for text in _texts(board))


def test_a_played_wu_is_element_coloured_on_the_board(state, card):
    duel = DuelState(stage=6, rounds=[Round(player=Side(queue=[card(SILVER_MANTA_RAY)]))])

    styles = _styles_over(_board_text(duel, state), "Silver Manta Ray")

    assert any(COLORS["water"] in style for style in styles)


def test_the_prize_wu_is_element_coloured_on_the_board(state, card):
    duel = DuelState(stage=2, stakes=card(LONGI_SASH))

    styles = _styles_over(_board_text(duel, state), "Longi Sash")

    assert any(COLORS["fire"] in style for style in styles)


def test_a_missing_wu_fails_the_style_lookup(state):
    """Guards the helper itself: a name that is not drawn must not read as "no colour"."""
    board = _board_text(DuelState(stage=1), state)

    with pytest.raises(AssertionError):
        _styles_over(board, "Wu That Does Not Exist")


def test_an_empty_queue_renders_a_dash(state):
    assert "Offensive: —" in _plain(_board_text(DuelState(stage=1), state))


def _line(board: RenderableType, prefix: str, *, side: str = "P1") -> str:
    """``side``'s board line starting with ``prefix``.

    Scoped to one duelist: both sides have an "Offensive:" line, so an unscoped search silently
    reads P1's when the test means P2's. Raises rather than let an ``in`` assertion match nothing.
    """
    lines = _plain(board).splitlines()
    for index, line in enumerate(lines):
        if not line.startswith(side):
            continue
        for own in lines[index + 1 :]:
            if own[:1] not in (" ", "\t"):  # the next side's header ends this one
                break
            if own.strip().startswith(prefix):
                return own.strip()
    raise AssertionError(f"{side} has no line starting with {prefix!r}:\n{_plain(board)}")


# --- played vs suffered: the queue mixes them, the board must not ----------------


def _cursed_duel(card):
    """P1 boosts then plays a curse; P2 answers with a curse of its own."""
    duel = DuelState(stage=6, challenge="force", background="wind", rounds=[Round(stat="force")])
    duel.round.player.queue.append(card(WUSHU_BRACELET))
    resolve_played_power(duel.round, card(SILK_SPITTER), is_player=True, element="wind")
    resolve_played_power(duel.round, card(JU_JU_FLYTRAP), is_player=False, element="wind")
    return duel


def test_a_curse_the_opponent_cast_is_not_listed_as_a_wu_you_played(state, card):
    board = _board_text(_cursed_duel(card), state)

    assert "Ju-Ju Flytrap" not in _line(board, "Offensive:", side="P1")


def test_a_curse_the_opponent_cast_is_listed_against_you(state, card):
    board = _board_text(_cursed_duel(card), state)

    assert "Ju-Ju Flytrap" in _line(board, "Defensive:", side="P1")


def test_a_curse_you_cast_leaves_your_own_line(state, card):
    """It spends your copy to land the harm opposite, so it prints once — on the side it acts."""
    board = _board_text(_cursed_duel(card), state)

    assert _line(board, "Offensive:", side="P1") == "Offensive: —"


def test_a_curse_you_cast_shows_on_the_line_of_whoever_wears_it(state, card):
    """Guards the test above: the Wu must move to the victim, not disappear from the board."""
    board = _board_text(_cursed_duel(card), state)

    assert "Silk Spitter" in _line(board, "Defensive:", side="P2")


def test_a_showdown_without_curses_still_shows_an_empty_defensive_line(state, card):
    """A dash reads as "nothing landed on me"; a missing line reads as a bug."""
    duel = DuelState(stage=6, challenge="force", background="metal", rounds=[Round(stat="force")])
    resolve_played_power(duel.round, card(FIST_OF_TEBIGONG), is_player=True, element="metal")

    assert _line(_board_text(duel, state), "Defensive:") == "Defensive: —"


def test_a_booster_is_joined_to_the_wu_it_boosts(state, card):
    """One play, not two entries — the ``+`` says the pair resolved together, booster first."""
    duel = DuelState(stage=6, challenge="force", background="metal", rounds=[Round(stat="force")])
    duel.round.player.queue.append(card(WUSHU_BRACELET))  # queued at the boost stage, before the card
    resolve_played_power(duel.round, card(FIST_OF_TEBIGONG), is_player=True, element="metal")

    line = _line(_board_text(duel, state), "Offensive:")

    assert "Wushu Bracelet" in line.split("+ Fist of Tebigong")[0]


def test_a_dragon_is_joined_to_the_wu_after_it_too(state, card):
    """The ``+`` marks the boost slot, not amplification: boost/0 lands there as much as boost/+1."""
    duel = DuelState(stage=6, challenge="force", background="metal", rounds=[Round(stat="force")])
    duel.round.player.queue.append(card(SILVER_MANTA_RAY))
    resolve_played_power(duel.round, card(FIST_OF_TEBIGONG), is_player=True, element="metal")

    assert "+ Fist of Tebigong" in _line(_board_text(duel, state), "Offensive:")


def test_a_mirrored_booster_is_joined_to_the_curse_it_doubled(state, card):
    """The mirror is inert, so only the duel knows it amplifies — the board must still say so."""
    line = _line(_board_text(_cursed_duel(card), state), "Defensive:", side="P2")

    assert "+ Silk Spitter" in line
    assert line.index("Wushu Bracelet") < line.index("Silk Spitter")


def test_unrelated_wu_are_comma_separated(state, card):
    """Guards the two above: the ``+`` must mean boosting, not merely 'next to'."""
    duel = DuelState(stage=6, challenge="force", background="wind", rounds=[Round(stat="force")])
    resolve_played_power(duel.round, card(SILK_SPITTER), is_player=True, element="wind")
    resolve_played_power(duel.round, card(JU_JU_FLYTRAP), is_player=False, element="wind")

    assert " + " not in _line(_board_text(duel, state), "Offensive:", side="P1")


def test_a_boosted_curse_lands_twice_the_harm(state, card):
    """Guards the ordering test above: without the booster's mirror there is nothing to order."""
    duel = _cursed_duel(card)

    harm = sum(c.stats["agility"] for c in duel.round.bot.suffered)

    assert harm == -2  # Silk Spitter's -1, doubled by the Wushu Bracelet


def test_a_wu_that_moves_no_stat_still_shows_because_you_played_it(state, card):
    """The board prints what is on the table, not what is winning.

    A booster fielded as an ordinary Wu lends nothing, and 0/0/0 is exactly what a player needs to
    see: a Wu they were forced to spend and got nothing for. Hiding it makes a staked Wu look unplayed.
    """
    duel = DuelState(stage=6, challenge="force", background="metal", rounds=[Round(stat="force", player=Side(queue=[card(WUSHU_BRACELET)]))])
    duel.round.player.queue[0].stats = {"force": 0, "agility": 0, "intellect": 0}

    line = _line(_board_text(duel, state), "Offensive:")

    assert "Wushu Bracelet" in line
    assert "0/0/0" in line


def test_an_unresolved_booster_stays_on_the_board(state, card):
    """At the power stage its stats are ``None`` — unresolved, not zero. It must not vanish."""
    duel = DuelState(stage=4, challenge="force", background="metal", rounds=[Round(stat="force", player=Side(queue=[card(WUSHU_BRACELET)]))])

    assert "Wushu Bracelet" in _line(_board_text(duel, state), "Offensive:")


# --- the elemental bonus, made visible -------------------------------------------


def test_a_resonant_wu_shows_the_value_the_background_lifts_it_to(state, card):
    """Printed 1 on the contested stat, worth 2 in water. The printed value is struck, not the name."""
    duel = DuelState(stage=6, challenge="force", background="water", rounds=[Round(stat="force", player=Side(queue=[card(SILVER_MANTA_RAY)]))])

    assert "Silver Manta Ray (1⌞₂/1/1)" in _line(_board_text(duel, state), "Offensive:")


def test_an_opposed_wu_shows_the_value_the_background_drags_it_to(state, card):
    """Metal on water is opposed: it scores one less than it prints, and the board says so.

    The numbers are read off the card, not restated — this test is about the *rendering* of a shift,
    and it must keep holding when the Fist is rebalanced.
    """
    fist = card(FIST_OF_TEBIGONG)
    printed = fist.stats["force"]
    duel = DuelState(stage=6, challenge="force", background="water", rounds=[Round(stat="force", player=Side(queue=[fist]))])

    shown = f"Fist of Tebigong ({printed}⌞{_subscript(printed - 1)}/0/0)"
    assert shown in _line(_board_text(duel, state), "Offensive:")


def test_the_struck_value_is_the_printed_one(state, card):
    """Guards the two above: strike what the card prints, subscript what it is worth."""
    fist = card(FIST_OF_TEBIGONG)
    printed = fist.stats["force"]
    effective = _subscript(printed - 1)  # metal, dragged down by a water arena
    duel = DuelState(stage=6, challenge="force", background="water", rounds=[Round(stat="force", player=Side(queue=[fist]))])
    board = _board_text(duel, state)

    assert f"{printed}⌞{effective}" in _line(board, "Offensive:")
    # Anchored to the shift itself. A bare "5" matches the first 5 anywhere on the board — a base
    # stat, a point total — and the styles come back from whatever that was.
    assert any("strike" in style for style in _styles_over(board, f"{printed}⌞"))
    assert not any("strike" in style for style in _styles_over(board, f"⌞{effective}"))


def test_the_shift_lands_on_whichever_stat_is_contested(state, card):
    """The elemental bonus only touches the challenge stat — here agility, not force."""
    duel = DuelState(stage=6, challenge="agility", background="water", rounds=[Round(stat="agility", player=Side(queue=[card(SILVER_MANTA_RAY)]))])

    assert "Silver Manta Ray (1/1⌞₂/1)" in _line(_board_text(duel, state), "Offensive:")


def test_a_voided_elemental_bonus_shifts_nothing(state, card):
    """A played Serpent's Tail kills the bonus, so no Wu may show a value it will not score."""
    duel = DuelState(stage=6,
        challenge="force",
        background="water",
        elemental_bonus_cancelled=True, rounds=[Round(player=Side(queue=[card(SILVER_MANTA_RAY)]))])

    assert "Silver Manta Ray (1/1/1)" in _line(_board_text(duel, state), "Offensive:")


def test_a_wu_name_carries_no_underline_or_strike(state, card):
    """The mark belongs on the number the background changes, not on the name."""
    duel = DuelState(stage=6, challenge="force", background="water", rounds=[Round(stat="force", player=Side(queue=[card(SILVER_MANTA_RAY)]))])

    styles = _styles_over(_board_text(duel, state), "Silver Manta Ray")

    assert not any("underline" in style or "strike" in style for style in styles)


def test_a_rule_separates_the_prize_from_the_cards_in_play(state, card):
    """The prize is not in play — it must read apart from the cards that are."""
    board = _plain(_board_text(DuelState(stage=2, stakes=card(LONGI_SASH))  , state))

    assert "─" * 10 in board


def test_the_rule_is_drawn_even_when_there_is_no_prize_yet(state):
    """An underline would vanish here; a drawn rule must not."""
    assert "─" * 10 in _plain(_board_text(DuelState(stage=1), state))


def test_the_prize_name_carries_no_underline(state, card):
    duel = DuelState(stage=2, stakes=card(LONGI_SASH))

    styles = _styles_over(_board_text(duel, state), "Longi Sash")

    assert not any("underline" in style for style in styles)


def test_the_background_carries_its_element_colour(state):
    duel = DuelState(stage=6, challenge="force", background="fire")

    styles = _styles_over(_board_text(duel, state), "FIRE")

    assert any(COLORS["fire"] in style for style in styles)


# --- the board must add up ---------------------------------------------------------


def _line_text(board: RenderableType, prefix: str, *, side: str = "P1") -> Text:
    """The ``Text`` object behind :func:`_line`, spans intact."""
    seen_side = False
    for text in _texts(board):
        if text.plain.startswith(side):
            seen_side = True
        elif seen_side and text.plain.strip().startswith(prefix):
            return text
    raise AssertionError(f"{side} has no {prefix!r} line")


def _effective_values(text: Text) -> str:
    """The line with every printed (struck) value removed and the brackets unwrapped.

    A shifted stat renders the printed value struck, with the value that counts subscripted inside
    brackets (``4̶⌞₃``). Drop the struck half, the stroke, the subscripting — what remains is what scores.
    """
    struck = {
        index
        for span in text.spans
        if "strike" in str(span.style)
        for index in range(span.start, span.end)
    }
    kept = "".join(ch for index, ch in enumerate(text.plain) if index not in struck)
    return kept.replace("⌞", "").translate(_FROM_SUBSCRIPT)


_FROM_SUBSCRIPT = str.maketrans("₀₁₂₃₄₅₆₇₈₉₋", "0123456789-")
_TO_SUBSCRIPT = str.maketrans("0123456789-", "₀₁₂₃₄₅₆₇₈₉₋")


def _subscript(value: int) -> str:
    """The value that *counts*, as the board draws it — beneath the struck printed one."""
    return str(value).translate(_TO_SUBSCRIPT)


def _contested_column(line: str) -> list[str]:
    """The contested (first) stat cell of every ``(...)`` group on a board line."""
    return [chunk.split(")")[0].split("/")[0].strip() for chunk in line.split("(")[1:]]


def test_a_curse_resonating_with_the_background_bites_deeper(state, card):
    """Silk Spitter is water. Cast on a water background, its harm sharpens: 0 -> -1."""
    duel = DuelState(stage=6, challenge="force", background="water", rounds=[Round(stat="force")])
    resolve_played_power(duel.round, card(SILK_SPITTER), is_player=False, element="water")

    spitter = card(SILK_SPITTER)
    force, agility, intellect = spitter.stats.values()
    shown = f"Silk Spitter ({force}⌞{_subscript(force - 1)}/{agility}/{intellect})"
    assert shown in _line(_board_text(duel, state), "Defensive:", side="P1")


def test_a_curse_the_background_turns_against_lands_softer(state, card):
    """Two-Ton Tunic is metal. On water the background opposes it, so its harm eases: -4 -> -3."""
    duel = DuelState(stage=6, challenge="force", background="water", rounds=[Round(stat="force")])
    resolve_played_power(duel.round, card(TWO_TON_TUNIC), is_player=False, element="water")

    tunic_force = card(TWO_TON_TUNIC).stats["force"]  # negative: it is a wound
    softened = _subscript(tunic_force + 1)  # the arena turns against it, so it bites one less deep
    shown = f"Two-Ton Tunic ({tunic_force}⌞{softened}/0/0)"
    assert shown in _line(_board_text(duel, state), "Defensive:", side="P1")


def test_the_same_wu_shifts_the_other_way_when_you_play_it(state, card):
    """Guards the sign: what lifts a Wu you played must drag down the same Wu cast at you."""
    duel = DuelState(stage=6, challenge="force", background="water", rounds=[Round(stat="force", player=Side(queue=[card(SILK_SPITTER)]))])

    spitter = card(SILK_SPITTER)
    force, agility, intellect = spitter.stats.values()
    shown = f"Silk Spitter ({force}⌞{_subscript(force + 1)}/{agility}/{intellect})"
    assert shown in _line(_board_text(duel, state), "Offensive:")


def test_the_printed_shifts_sum_to_the_total_beside_base(state, card):
    """base + what Offensive is *worth* + what Defensive *lands* == the score the header shows.

    The elemental bonus is earned only by the Offensive line, so the board can show its arithmetic.
    A player who adds up the numbers must reach the number we printed for them.
    """
    duel = DuelState(stage=6, challenge="force", background="water", rounds=[Round(stat="force")])
    duel.round.player.queue.append(card(SILVER_MANTA_RAY))  # water on water: 1 -> 2
    resolve_played_power(duel.round, card(FIST_OF_TEBIGONG), is_player=True, element="water")  # metal: 4 -> 3
    resolve_played_power(duel.round, card(TWO_TON_TUNIC), is_player=False, element="water")  # cursed at P1

    from xiaolin_showdown.logic.mechanics.scoring import contributing, count_end_stats

    total = count_end_stats(
        "force", 1, duel.round.player.queue, state.player.character.stats, "water",
        earns_bonus=duel.round.player.contributors(),
        suffers_bonus=contributing(duel.round.player.suffered),
    )
    duel.round.player.result = [total, 0, 0]
    board = _board_text(duel, state)

    # a shifted stat prints the struck original next to the real one; drop the struck half
    worth = sum(
        int(cell)
        for row in ("Offensive:", "Defensive:")
        for cell in _contested_column(_effective_values(_line_text(board, row)))
    )

    assert state.player.character.stats["force"] + worth == total
    assert worth != 0  # the duel actually put something on the table


# --- the board names the phase by what this duelist did ----------------------------


def test_setup_reads_as_challenge_when_you_hold_priority(state):
    duel = DuelState(stage=2, player_priority=True, challenge="force", background="water")

    assert "Challenge" in _plain(_board_text(duel, state)).splitlines()[0]


def test_setup_reads_as_background_when_your_opponent_leads(state):
    """One stage, two moves: you answer with the element when you did not name the stat."""
    duel = DuelState(stage=2, player_priority=False, challenge="force", background="water")

    assert "Background" in _plain(_board_text(duel, state)).splitlines()[0]


# --- the priority star explains itself on hover -------------------------------------


def test_the_priority_star_carries_a_challenger_tooltip(state):
    """The star means "names the challenge, and breaks a tie" — say so on hover."""
    duel = DuelState(stage=2, player_priority=True, challenge="force", background="water")

    tooltips = {
        span.style.meta.get("tooltip")
        for text in _texts(_board_text(duel, state))
        for span in text.spans
        if hasattr(span.style, "meta")
    }

    assert "Challenger" in tooltips


def test_only_the_duelist_with_priority_gets_the_star(state):
    duel = DuelState(stage=2, player_priority=False, challenge="force", background="water")

    assert _plain(_board_text(duel, state)).count("✫") == 1


def test_a_tournament_names_the_battle_and_the_stat_it_contests(state):
    duel = DuelState(stage=4, challenge=TOURNAMENT, background="water", rounds=[Round(stat="force")])

    board = _plain(_board_text(duel, state))

    assert "Battle 1 of 3 (FORCE)" in board


def test_a_tournament_shows_no_empty_brackets_before_a_battle_is_on_the_table(state):
    """The stat is only known once a battle opens. An empty "()" reads as a bug, not as nothing."""
    duel = DuelState(stage=2, challenge=TOURNAMENT, background="water", rounds=[Round()])

    board = _plain(_board_text(duel, state))

    assert "()" not in board
    assert "Battle 1 of 3" in board


def _rendered(renderable, width: int) -> list[str]:
    console = Console(width=width, legacy_windows=False, file=io.StringIO())
    with console.capture() as capture:
        console.print(renderable)
    return [line.rstrip() for line in capture.get().splitlines()]


def test_a_long_line_of_wu_breaks_between_them_never_inside_one(card):
    """A Wu is its name and the stats it scores for. Split them and the board says nothing."""
    cards = [card(SILVER_MANTA_RAY), card(FIST_OF_TEBIGONG), card(WUSHU_BRACELET), card(SILK_SPITTER)]
    line = _cards_line("Offensive", cards, [], "force", "water")

    rendered = _rendered(line, 58)

    assert len(rendered) > 1, "the line did not wrap — widen the sample or narrow the console"
    for text in rendered:
        opened, closed = text.count("("), text.count(")")
        assert opened == closed, f"a Wu was split across the break: {text!r}"


@pytest.mark.parametrize("label", ["Offensive", "Defensive"])
def test_a_wrapped_line_continues_under_the_first_wu_not_the_label(card, label):
    """A continuation starts where the Wu start, whatever the label is and whatever the first Wu is.

    The label is a tag, not content: a row continuing beneath it reads as a second, unlabelled row.
    """
    cards = [card(SILVER_MANTA_RAY), card(FIST_OF_TEBIGONG), card(WUSHU_BRACELET), card(SILK_SPITTER)]
    line = _cards_line(label, cards, [], "force", "water")

    rendered = _rendered(line, 58)
    content_starts_at = line.label.cell_len  # the column the first Wu begins in

    assert len(rendered) > 1, "the line did not wrap — nothing to check"
    assert rendered[0].index(card(SILVER_MANTA_RAY).name) == content_starts_at
    for text in rendered[1:]:
        indent = len(text) - len(text.lstrip())
        assert indent == content_starts_at, f"continued under the label, not the Wu: {text!r}"
