"""Falcon's Eye / Eagle Scope — printed sisters (each names the other in its own card text). Held
together, they combine into Farsight: reveal the pile as deep as Teleskopia ever could, then set what
was seen back down in whichever order the caster chooses. Both Wu are spent for it, no points banked."""

from __future__ import annotations

from copy import deepcopy

from termcade.core.rng import Rng

from xiaolin_showdown.logic.flow.actions import can_farsight, farsight
from xiaolin_showdown.logic.mechanics.powers import SCOPE_DEPTH
from xiaolin_showdown.logic.schema.catalog import load_catalog
from xiaolin_showdown.logic.schema.constants import EAGLE_SCOPE_ID, FALCONS_EYE_ID, in_pool
from xiaolin_showdown.logic.config.settings import XiaolinSettings
from xiaolin_showdown.logic.flow.setup import new_game
from xiaolin_showdown.logic.schema.state import XiaolinState

CAT = load_catalog()
DEFAULT = XiaolinSettings()
WUYA = next(c for c in CAT.characters if c.name == "Wuya")


def _state() -> XiaolinState:
    return new_game(CAT, Rng(1), CAT.character(1), opponent=CAT.character(2))


def _wuya_state() -> XiaolinState:
    return new_game(CAT, Rng(1), WUYA, opponent=CAT.character(2))


def _clear_sisters(state: XiaolinState) -> None:
    """The seeded deal can hand out either sister on its own; strip both so a test's own appends are
    the only ones in play — the same reason `test_yin_yang_yoyo._clear_yoyo_halves` exists."""
    stray = {FALCONS_EYE_ID, EAGLE_SCOPE_ID}
    state.player.hand = [card for card in state.player.hand if card.id not in stray]


def _give_both_sisters(state: XiaolinState) -> None:
    state.player.hand.append(deepcopy(CAT.card(FALCONS_EYE_ID)))
    state.player.hand.append(deepcopy(CAT.card(EAGLE_SCOPE_ID)))


def test_can_farsight_needs_both_sisters_in_hand():
    state = _state()
    _clear_sisters(state)
    state.player.hand.append(deepcopy(CAT.card(FALCONS_EYE_ID)))
    assert can_farsight(state, 1) is False
    state.player.hand.append(deepcopy(CAT.card(EAGLE_SCOPE_ID)))
    assert can_farsight(state, 1) is True


def test_can_farsight_needs_a_pile_to_rearrange():
    state = _state()
    _clear_sisters(state)
    _give_both_sisters(state)
    state.card_deck = []
    assert can_farsight(state, 1) is False


def test_can_farsight_needs_the_turns_action_unspent():
    state = _state()
    _clear_sisters(state)
    _give_both_sisters(state)
    state.actions_taken = 1
    assert can_farsight(state, 1) is False


def test_farsight_consumes_both_sisters_and_spends_the_action():
    state = _state()
    _clear_sisters(state)
    _give_both_sisters(state)
    order = list(reversed(state.card_deck[:SCOPE_DEPTH]))
    farsight(state, order, DEFAULT)
    ids = [card.id for card in state.player.hand]
    assert FALCONS_EYE_ID not in ids
    assert EAGLE_SCOPE_ID not in ids
    assert state.actions_taken == 1


def test_farsight_sets_the_pile_back_down_in_the_chosen_order():
    state = _state()
    _clear_sisters(state)
    _give_both_sisters(state)
    untouched = state.card_deck[SCOPE_DEPTH:]
    order = list(reversed(state.card_deck[:SCOPE_DEPTH]))
    farsight(state, order, DEFAULT)
    assert state.card_deck[:SCOPE_DEPTH] == order
    assert state.card_deck[SCOPE_DEPTH:] == untouched


def test_farsight_never_touches_the_pile_past_scope_depth():
    state = _state()
    _clear_sisters(state)
    _give_both_sisters(state)
    beyond = state.card_deck[SCOPE_DEPTH]
    farsight(state, list(reversed(state.card_deck[:SCOPE_DEPTH])), DEFAULT)
    assert state.card_deck[SCOPE_DEPTH] is beyond


def test_wuya_keeps_both_sisters_and_wears_them_instead_of_spending_them():
    state = _wuya_state()
    _clear_sisters(state)
    _give_both_sisters(state)
    order = list(reversed(state.card_deck[:SCOPE_DEPTH]))
    farsight(state, order, DEFAULT)
    ids = [card.id for card in state.player.hand]
    assert FALCONS_EYE_ID in ids
    assert EAGLE_SCOPE_ID in ids
    assert all(card.uses == 1 for card in state.player.hand if card.id in (FALCONS_EYE_ID, EAGLE_SCOPE_ID))
    assert state.actions_taken == 1


def test_wuya_wear_vaults_a_sister_that_hits_its_own_third_use():
    state = _wuya_state()
    _clear_sisters(state)
    _give_both_sisters(state)
    worn_out = next(c for c in state.player.hand if c.id == FALCONS_EYE_ID)
    worn_out.uses = DEFAULT.wear_limit - 1  # this use is its third
    points_before = state.player.points
    farsight(state, list(reversed(state.card_deck[:SCOPE_DEPTH])), DEFAULT)
    ids = [card.id for card in state.player.hand]
    assert FALCONS_EYE_ID not in ids  # vaulted, not spent — banked below, not the used pile
    assert worn_out not in state.used
    assert state.player.points == points_before + worn_out.points
    fresh = next(c for c in state.player.hand if c.id == EAGLE_SCOPE_ID)
    assert fresh.uses == 1  # its own first use, unaffected by its sister wearing out


def test_falcons_eye_and_eagle_scope_can_be_dealt_together():
    """Neither sister is a signature Wu or a combine-only card like the Yo-Yo halves — both stay in
    the ordinary pool, reachable without Farsight ever being forced."""
    assert in_pool(FALCONS_EYE_ID)
    assert in_pool(EAGLE_SCOPE_ID)
