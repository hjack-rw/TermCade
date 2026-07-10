"""Why a vault action is out of reach — the text the greyed action shows on hover.

The ``can_*`` predicates are defined as "no reason", so the invariant worth pinning is that a reason
exists exactly when the action is blocked. Each case below drives that across a state where the
action *is* allowed and one where it is not, since an invariant checked on one branch is not checked.
"""

from __future__ import annotations

import pytest

from xiaolin_showdown.logic.actions import (
    can_deposit,
    can_draw,
    deposit_blocked,
    draw_blocked,
    usable_powers,
    use_power_blocked,
)

BRAS_FINGER = 16  # a `deposit`-trigger Wu: usable only while a deposit is still allowed
PLAIN_WU = 6
ANOTHER_PLAIN_WU = 7


# --- the reason and the predicate never disagree --------------------------------


@pytest.mark.parametrize("spend_draw", [False, True])
def test_a_draw_reason_exists_exactly_when_the_draw_is_blocked(state, settings, card, spend_draw):
    state.player.deck = [card(PLAIN_WU)]  # otherwise a draw is always blocked, testing one branch
    if spend_draw:
        state.draw_counter = settings.draw_limit

    assert (draw_blocked(state, settings) is None) is can_draw(state, settings)


@pytest.mark.parametrize("spend_deposit", [False, True])
def test_a_deposit_reason_exists_exactly_when_the_deposit_is_blocked(state, settings, spend_deposit):
    if spend_deposit:
        state.deposit_counter = settings.deposit_limit

    limit = settings.deposit_limit
    assert (deposit_blocked(state, limit) is None) is can_deposit(state, limit)


@pytest.mark.parametrize("hand_ids", [[PLAIN_WU, ANOTHER_PLAIN_WU], [BRAS_FINGER, PLAIN_WU]])
def test_a_power_reason_exists_exactly_when_no_power_is_usable(state, settings, card, hand_ids):
    state.player.hand = [card(card_id) for card_id in hand_ids]

    limit = settings.deposit_limit
    allowed = use_power_blocked(state, limit) is None
    assert allowed is bool(usable_powers(state, limit))


# --- each reason names the rule that stopped you --------------------------------


def test_a_spent_draw_says_so(state, settings):
    state.draw_counter = settings.draw_limit
    assert draw_blocked(state, settings) == "Already drawn this turn."


def test_an_empty_personal_deck_says_so(state, settings):
    state.player.deck = []
    assert draw_blocked(state, settings) == "Your personal deck is empty."


def test_a_full_hand_says_so(state, settings, card):
    state.player.deck = [card(PLAIN_WU)]
    state.player.hand = [card(PLAIN_WU) for _ in range(settings.max_hand_size)]
    assert draw_blocked(state, settings) == "Your hand is full."


def test_a_spent_deposit_says_so(state, settings):
    state.deposit_counter = settings.deposit_limit
    assert deposit_blocked(state, settings.deposit_limit) == "Already deposited this turn."


def test_a_last_wu_cannot_be_deposited(state, settings, card):
    state.player.hand = [card(PLAIN_WU)]
    assert deposit_blocked(state, settings.deposit_limit) == "Only one Wu left in hand."


def test_a_hand_of_plain_wu_has_no_power_to_use(state, settings, card):
    state.player.hand = [card(PLAIN_WU), card(ANOTHER_PLAIN_WU)]
    assert use_power_blocked(state, settings.deposit_limit) == "No Wu with a usable power."


def test_a_deposit_power_is_out_of_reach_once_the_deposit_is_spent(state, settings, card):
    """A `deposit`-trigger Wu only counts while a deposit is allowed — say *that*, not "no power"."""
    state.player.hand = [card(BRAS_FINGER), card(PLAIN_WU)]
    state.deposit_counter = settings.deposit_limit

    assert use_power_blocked(state, settings.deposit_limit) == "Already deposited this turn."


def test_a_usable_power_has_no_reason(state, settings, card):
    state.player.hand = [card(BRAS_FINGER), card(PLAIN_WU)]
    assert use_power_blocked(state, settings.deposit_limit) is None


# --- and the vault shows it -----------------------------------------------------


async def test_a_blocked_action_explains_itself_on_hover(state, settings, open_vault, tooltips_in):
    state.draw_counter = settings.draw_limit

    async with open_vault(state) as (app, _pilot):
        assert "Already drawn this turn." in tooltips_in(app, "#actions")


async def test_an_available_action_still_describes_itself(state, open_vault, tooltips_in):
    async with open_vault(state) as (app, _pilot):
        assert "Duel for the next Wu on the pile." in tooltips_in(app, "#actions")
