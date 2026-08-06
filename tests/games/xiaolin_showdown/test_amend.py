"""The Hodoku Mouse (AMEND): a temple action, taken back.

Spent at the temple it restores the board to just before your last action — the RNG stream with it —
and is consumed doing it (one undo per Mouse). It is only ever offered when there is something to
undo, which in a one-action turn there never is.
"""

from __future__ import annotations

from copy import deepcopy

from termcade.core.rng import Rng

from xiaolin_showdown.logic.config.settings import XiaolinSettings
from xiaolin_showdown.logic.flow.actions import deposit, usable_powers, use_power
from xiaolin_showdown.logic.mechanics.powers import Mechanic, mechanic_of

DEFAULT = XiaolinSettings()


def _mouse_card(catalog):
    """The Hodoku Mouse — the only AMEND-mechanic Wu, so the mechanic alone finds it."""
    return next(c for c in catalog.cards if mechanic_of(c.power) is Mechanic.AMEND)


def _gamble_card(catalog):
    """Ohwah Tegu Saim — the only GAMBLE-mechanic Wu."""
    return next(c for c in catalog.cards if mechanic_of(c.power) is Mechanic.GAMBLE)


def _seed_mouse(state):
    """Put a Mouse in hand and return (mouse, a non-Mouse card to spend).

    The dealt hand can hold a stray Mouse of its own — strip it first, so the one seeded here is the
    only AMEND card in play."""
    state.player.hand = [c for c in state.player.hand if mechanic_of(c.power) is not Mechanic.AMEND]
    mouse = deepcopy(_mouse_card(state.catalog))
    state.player.hand.append(mouse)
    victim = next(c for c in state.player.hand if mechanic_of(c.power) is not Mechanic.AMEND)
    return mouse, victim


def test_amend_puts_the_points_back(state):
    rng = Rng(1)
    mouse, victim = _seed_mouse(state)
    before = state.player.points

    deposit(state, victim, rng=rng)  # banks the victim, and stashes the board first
    assert state.player.points != before  # sanity: the deposit moved points
    use_power(state, mouse, DEFAULT, is_player=True, rng=rng)

    assert state.player.points == before


def test_amend_puts_the_spent_wu_back_in_hand(state):
    rng = Rng(1)
    mouse, victim = _seed_mouse(state)

    deposit(state, victim, rng=rng)
    use_power(state, mouse, DEFAULT, is_player=True, rng=rng)

    assert any(c.id == victim.id for c in state.player.hand)


def test_amend_spends_the_mouse(state):
    rng = Rng(1)
    mouse, victim = _seed_mouse(state)

    deposit(state, victim, rng=rng)
    use_power(state, mouse, DEFAULT, is_player=True, rng=rng)

    assert not any(mechanic_of(c.power) is Mechanic.AMEND for c in state.player.whole_hand)


def test_the_undone_mouse_lands_in_the_used_pile(state):
    rng = Rng(1)
    mouse, victim = _seed_mouse(state)

    deposit(state, victim, rng=rng)
    use_power(state, mouse, DEFAULT, is_player=True, rng=rng)

    assert any(mechanic_of(c.power) is Mechanic.AMEND for c in state.used)


def test_amend_restores_the_rng_stream(state):
    """A gamble deposit rolls the hidden stream; undoing it must wind the stream back too, or the
    next roll comes out different from the one the undone action already saw."""
    rng = Rng(1)
    gamble = deepcopy(_gamble_card(state.catalog))
    state.player.hand.append(gamble)
    mouse = deepcopy(_mouse_card(state.catalog))
    state.player.hand.append(mouse)
    before = rng.get_state()

    deposit(state, gamble, rng=rng)  # rolls: advances the stream
    assert rng.get_state() != before  # sanity: the gamble consumed the stream
    use_power(state, mouse, DEFAULT, is_player=True, rng=rng)

    assert rng.get_state() == before


def test_the_mouse_is_hidden_with_nothing_to_undo(state):
    """No action taken yet this turn — so nothing to fix, and the Mouse is not offered. This is also
    what keeps it useless in a one-action turn: the stash is only ever set by an action already spent."""
    _seed_mouse(state)

    offered = [c for c in usable_powers(state, 3, DEFAULT) if mechanic_of(c.power) is Mechanic.AMEND]

    assert not offered


def test_the_mouse_is_offered_once_an_action_can_be_undone(state):
    """A boss turn's second action: one already spent (stashed), budget still open."""
    rng = Rng(1)
    _mouse, victim = _seed_mouse(state)

    deposit(state, victim, rng=rng)  # spends action 1 of the turn, stashing the board
    offered = [c for c in usable_powers(state, 3, DEFAULT) if mechanic_of(c.power) is Mechanic.AMEND]

    assert offered
