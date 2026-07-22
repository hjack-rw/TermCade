"""A duelist's name, shortened where the row cannot afford it.

The rule fires on what a name COSTS, not on how many words it has — which is the whole reason it is
a threshold and not a split. Every assertion here reads the roster rather than restating it, so a
new character joins the rule instead of quietly escaping it.
"""

from __future__ import annotations

import pytest

from xiaolin_showdown.logic.catalog import load_catalog
from xiaolin_showdown.screens.format import SHORTEN_OVER, display_name

ROSTER = [character.name for character in load_catalog().characters]


def test_a_short_name_is_left_alone() -> None:
    assert display_name("Omi", short=True) == "Omi"


def test_a_long_name_keeps_only_its_first_word() -> None:
    assert display_name("Salvador_Cumo", short=True) == "Salvador"
    assert display_name("Hannibal_Roy_Bean", short=True) == "Hannibal"


def test_a_two_word_name_short_enough_to_fit_stays_whole() -> None:
    """`Le Mime` is the reason the rule is a threshold. Splitting on the space leaves "Le", which
    is an article, not a name — and it was never the name costing the row its space."""
    assert display_name("Le_Mime", short=True) == "Le Mime"


@pytest.mark.parametrize("name", ROSTER)
def test_a_duelist_is_either_left_whole_or_cut_to_a_real_word(name: str) -> None:
    """The failure mode this guards is a name CUT down to something meaningless — "Le". A name that
    is simply short to begin with, like Omi, is not a fragment and is never touched, so the floor
    applies only where the rule actually fired."""
    full, shown = display_name(name), display_name(name, short=True)
    assert shown == full or len(shown) >= 4, f"{full!r} was cut to {shown!r}"


@pytest.mark.parametrize("name", ROSTER)
def test_shortening_never_makes_a_name_longer_than_the_threshold_allows(name: str) -> None:
    shown = display_name(name, short=True)
    assert len(shown) <= max(SHORTEN_OVER, len(name.split("_")[0]))


def test_the_full_name_is_still_what_a_desktop_sees() -> None:
    """`short` is opt-in. Nothing that has the width should be paying for a phone's problem."""
    assert display_name("Salvador_Cumo") == "Salvador Cumo"
    assert display_name("Salvador_Cumo", upper=True) == "SALVADOR CUMO"
