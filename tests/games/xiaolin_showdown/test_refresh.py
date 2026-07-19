"""Tong ku Reverso — Refresh calls the Wu most recently used by EITHER duelist back to your hand.

A Wu spent on its own power is discarded to a shared, ordered *used* pile (deposited Wu are banked
and gone, and never reach it). Refresh pops the newest off that pile into the caster's hand — yours
or your opponent's, whoever used it last. It fizzles when nobody has used anything, and the pile
survives a save.
"""

from __future__ import annotations

from xiaolin_showdown.logic.actions import usable_powers, use_power
from xiaolin_showdown.logic.mechanics.cards import is_one_of
from xiaolin_showdown.logic.models import Mechanic
from xiaolin_showdown.logic.state import XiaolinState

from factories import wu

DEPOSIT_LIMIT = 1


def _reverso():
    return wu(0, 0, 0, mechanic=Mechanic.REFRESH, name="Reverso")


def test_refresh_calls_back_the_last_used_wu(state):
    reverso = _reverso()
    spent = wu(1, name="Spent")
    state.player.hand = [reverso]
    state.used = [wu(2, name="Older"), spent]  # most recent last

    use_power(state, reverso, is_player=True)

    assert is_one_of(spent, state.player.hand)  # the last-used Wu came back
    assert not is_one_of(spent, state.used)  # and left the used pile


def test_refresh_takes_the_opponents_wu_when_it_was_used_last(state):
    reverso = _reverso()
    theirs = wu(1, name="Theirs")
    state.player.hand = [reverso]
    state.used = [wu(2, name="Mine"), theirs]  # the opponent used the most recent one

    use_power(state, reverso, is_player=True)

    assert is_one_of(theirs, state.player.hand)  # you take it into YOUR hand


def test_a_refreshed_wu_comes_back_healed(state):
    reverso = _reverso()
    worn = wu(1, name="Worn")
    worn.uses = 2  # two showdowns of wear on it
    state.player.hand = [reverso]
    state.used = [worn]

    use_power(state, reverso, is_player=True)

    assert worn.uses == 0  # healed — the wear is undone on the way back


def test_refresh_fizzles_with_nothing_used(state):
    reverso = _reverso()
    state.player.hand = [reverso]
    state.used = []

    message = use_power(state, reverso, is_player=True)

    assert "should have happened" in message.toast  # the fizzle wording


def test_a_used_power_lands_in_the_shared_pile(state):
    reverso = _reverso()
    state.player.hand = [reverso]
    state.used = [wu(1, name="Spent")]

    use_power(state, reverso, is_player=True)

    assert is_one_of(reverso, state.used)  # the fired Wu is spent into the shared pile, not vanished


def test_refresh_is_offered_only_with_a_used_wu(state):
    reverso = _reverso()
    state.player.hand = [reverso]

    state.used = []
    assert not is_one_of(reverso, usable_powers(state, DEPOSIT_LIMIT))

    state.used = [wu(1)]
    assert is_one_of(reverso, usable_powers(state, DEPOSIT_LIMIT))


def test_the_used_pile_round_trips_a_save(state):
    state.used = [state.catalog.card(6)]

    restored = XiaolinState.restore(state.snapshot(), None)

    assert [c.id for c in restored.used] == [6]
