"""Every mechanic is priced, or explicitly excused. A forgotten one is worth nothing, silently.

`duel_value` reads a card's *printed* stats. A Wu whose stats resolve when it is played prints
`? ? ?` or 0/0/0 — so the stats answer **zero**, and nothing anywhere complains. The opponent then
banks the strongest card in the game for two points, and prices a wager as though the slot were empty.

That is not a hypothetical. It is what happened to the pours and the three negations: five cards
worth nothing to the opponent, for a measured 16 points of its win rate, until a simulation caught it.
Nothing in the type system, the linter or the suite had anything to say.

So this file is the thing that has something to say. A new mechanic must be **priced** (an entry in
`_MECHANIC_VALUE`) or **excused** (declared in `_STATS_ARE_THE_WHOLE_VALUE`). It may not be forgotten.
"""

from __future__ import annotations

from xiaolin_showdown.logic.mechanics.powers import Mechanic, mechanic_of
from xiaolin_showdown.logic.turn import (
    _MECHANIC_VALUE,
    _STATS_ARE_THE_WHOLE_VALUE,
    _WORTH_NOTHING_ON_THE_TABLE,
    duel_value,
)


def test_every_mechanic_is_priced_or_excused():
    """The guard. Add a Mechanic and this fails until you have said what it is worth."""
    accounted = set(_MECHANIC_VALUE) | _STATS_ARE_THE_WHOLE_VALUE

    missing = set(Mechanic) - accounted
    assert not missing, (
        f"unpriced mechanic(s): {sorted(m.value for m in missing)} — a Wu carrying one is worth its "
        f"printed stats and nothing else, so a card that prints '? ? ?' reads as junk. Price it in "
        f"turn._MECHANIC_VALUE, or excuse it in turn._STATS_ARE_THE_WHOLE_VALUE."
    )


def test_a_mechanic_is_never_both_priced_and_excused():
    """The two sets are a decision, not a suggestion — a mechanic belongs to exactly one."""
    both = set(_MECHANIC_VALUE) & _STATS_ARE_THE_WHOLE_VALUE

    assert not both, f"priced AND excused: {sorted(m.value for m in both)}"


def test_no_wu_that_resolves_at_play_is_worth_nothing(catalog):
    """The bug itself, in the card DB: a Wu that prints no stats must not price at zero.

    The pours and the negations all print `? ? ?` or 0/0/0. If one of them values at zero, the easy
    opponent — which banks its *least* useful Wu — will cash it first, as junk.
    """
    for card in catalog.cards:
        prints_nothing = not any(value for value in card.stats.values())
        if not prints_nothing or mechanic_of(card.power) in _WORTH_NOTHING_ON_THE_TABLE:
            continue  # deck padding and the joke Wu are *meant* to be worth nothing on the table
        assert duel_value(card) > 0, (
            f"{card.name!r} prints no stats and prices at zero — the opponent will bank it as junk"
        )
