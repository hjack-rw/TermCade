"""Initiative sources: which Wu are credited, and how the vault shows them.

``initiative_sources`` must always agree with ``initiative`` — the bonuses it lists sum to the number
displayed beside them, or the tooltip lies.
"""

from __future__ import annotations

import pytest

from factories import duelist, initiative_wu, plain_wu, plain_wu_agility, wu

from xiaolin_showdown.logic.mechanics.scoring import initiative, initiative_sources
from xiaolin_showdown.logic.schema.catalog import load_catalog
from xiaolin_showdown.logic.schema.models import Card, Mechanic, Player
from xiaolin_showdown.screens.display.format import bonus_tooltip

_CAT = load_catalog()


def _wu(bonus: int) -> Card:
    # An initiative bonus rides on a passive `hand`/0 power (see catalog._power).
    return wu(mechanic=Mechanic.INITIATIVE, bonus=bonus)


def _duelist(*bonuses: int) -> Player:
    return duelist(hand=[_wu(bonus) for bonus in bonuses])


def _bonuses(cards: list[Card]) -> list[int]:
    return [card.power.initiative_bonus for card in cards]


# --- what the number is made of -------------------------------------------------


@pytest.mark.parametrize("side", [0, 1])
def test_the_listed_bonuses_sum_to_the_initiative(side):
    player, bot = _duelist(1, 2), _duelist(-1)

    assert sum(_bonuses(initiative_sources(player, bot)[side])) == initiative(player, bot)[side]


def test_a_repeated_bonus_is_credited_once():
    """Same bonuses don't stack — two +1 Wu list one +1."""
    sources, _ = initiative_sources(_duelist(1, 1), _duelist())
    assert _bonuses(sources) == [1]


def test_different_bonuses_all_stack():
    sources, _ = initiative_sources(_duelist(1, 2), _duelist())
    assert _bonuses(sources) == [1, 2]


def test_an_opponents_debuff_is_credited_to_this_side():
    sources, _ = initiative_sources(_duelist(), _duelist(-2))
    assert _bonuses(sources) == [-2]  # their card, our initiative


# --- how the vault shows it -----------------------------------------------------


def test_the_tooltip_lists_the_bonuses_in_round_brackets():
    assert bonus_tooltip([1, -1]) == "(+1, -1)"


def test_the_tooltip_marks_an_empty_bracket_when_nothing_applies():
    """A silent hover must mean "the cursor missed", never "this duelist has no buffs"."""
    assert bonus_tooltip([]) == "(/)"


async def test_each_duelist_row_gets_its_own_initiative_tooltip(
    state, card, open_vault, hover_tooltip
):
    """Both rows live in one Static, so the bonuses ride on each row's own span, not the widget."""
    state.player.hand = [card(initiative_wu(_CAT, 1).id)]
    state.bot.hand = [card(initiative_wu(_CAT, -1).id), card(initiative_wu(_CAT, 1).id)]

    async with open_vault(state) as (app, pilot):
        # From the right: the row's FIRST tooltip span is the training bar, initiative is rightmost.
        player_row = await hover_tooltip(app, pilot, "#state", row=0, from_right=True)
        bot_row = await hover_tooltip(app, pilot, "#state", row=1, from_right=True)

    assert (player_row, bot_row) == ("(+1, -1)", "(+1)")


async def test_a_duelist_with_no_bonuses_still_tooltips(state, card, open_vault, hover_tooltip):
    # Two interchangeable INNATE Wu (no queued power, no initiative bonus) — any two distinct ones do.
    state.player.hand = [card(plain_wu(_CAT).id)]
    state.bot.hand = [card(plain_wu_agility(_CAT).id)]

    async with open_vault(state) as (app, pilot):
        assert await hover_tooltip(app, pilot, "#state", row=0, from_right=True) == "(/)"
