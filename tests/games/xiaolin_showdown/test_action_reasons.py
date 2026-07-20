"""Why a vault action is out of reach — the text the greyed action shows on hover.

The ``can_*`` predicates are defined as "no reason", so the invariant worth pinning is that a reason
exists exactly when the action is blocked. Each case below drives that across a state where the
action *is* allowed and one where it is not, since an invariant checked on one branch is not checked.
"""

from __future__ import annotations

import pytest

from xiaolin_showdown.logic.actions import (
    SPENT_MESSAGE,
    can_deposit,
    can_draw,
    deposit_blocked,
    draw_blocked,
    draw_swaps,
    usable_powers,
    use_power_blocked,
)
from xiaolin_showdown.logic.settings import deposit_limit

BRAS_FINGER = 16  # a `deposit`-trigger Wu: usable only while a deposit is still allowed
PLAIN_WU = 6
ANOTHER_PLAIN_WU = 7


# --- the reason and the predicate never disagree --------------------------------


@pytest.mark.parametrize("spend_draw", [False, True])
def test_a_draw_reason_exists_exactly_when_the_draw_is_blocked(state, settings, card, spend_draw):
    state.player.deck = [card(PLAIN_WU)]  # otherwise a draw is always blocked, testing one branch
    if spend_draw:
        state.actions_taken = settings.actions_per_turn

    assert (draw_blocked(state, settings) is None) is can_draw(state, settings)


@pytest.mark.parametrize("spend_deposit", [False, True])
def test_a_deposit_reason_exists_exactly_when_the_deposit_is_blocked(state, settings, spend_deposit):
    if spend_deposit:
        state.actions_taken = settings.actions_per_turn

    limit = settings.actions_per_turn
    assert (deposit_blocked(state, limit) is None) is can_deposit(state, limit)


@pytest.mark.parametrize("hand_ids", [[PLAIN_WU, ANOTHER_PLAIN_WU], [BRAS_FINGER, PLAIN_WU]])
def test_a_power_reason_exists_exactly_when_no_power_is_usable(state, settings, card, hand_ids):
    state.player.hand = [card(card_id) for card_id in hand_ids]

    limit = settings.actions_per_turn
    allowed = use_power_blocked(state, limit) is None
    assert allowed is bool(usable_powers(state, limit))


# --- each reason names the rule that stopped you --------------------------------


def test_a_spent_action_blocks_a_draw(state, settings):
    """One budget, one message: banking, using a power and drawing all spend the same action."""
    state.actions_taken = settings.actions_per_turn
    assert draw_blocked(state, settings) == SPENT_MESSAGE


def test_an_empty_personal_deck_says_so(state, settings):
    state.player.deck = []
    assert draw_blocked(state, settings) == "Your personal deck is empty."


def test_a_full_hand_does_not_block_a_draw_it_swaps(state, settings, card):
    """A full hand used to block Draw. Now it SWAPS — shelve one, draw one — so a stuck hand can cycle."""
    state.player.deck = [card(PLAIN_WU)]
    state.player.hand = [card(PLAIN_WU) for _ in range(settings.max_hand_size)]

    assert draw_blocked(state, settings) is None  # allowed
    assert draw_swaps(state, settings) is True  # ...and it is a swap, not a growth


def test_a_spent_action_blocks_a_deposit(state, settings):
    state.actions_taken = settings.actions_per_turn
    assert deposit_blocked(state, settings.actions_per_turn) == SPENT_MESSAGE


def test_a_last_wu_cannot_be_deposited(state, settings, card):
    state.player.hand = [card(PLAIN_WU)]
    assert deposit_blocked(state, settings.actions_per_turn) == "Only one Wu left in hand."


def test_at_most_half_a_turns_actions_may_be_spent_depositing():
    """A bigger action budget buys TEMPO — a draw, a power, a stat — not a faster vault.

    Derived from the budget rather than pinned per tier, so it cannot drift out of step with it: the
    ordinary one-action turn is unchanged, and it binds only where the budget is larger.
    """
    assert deposit_limit(1) == 1
    assert deposit_limit(3) == 2


def test_a_turn_that_has_deposited_its_share_says_so(state, settings):
    """The cap is what keeps a larger action budget from simply being more banks a turn."""
    budget = settings.actions_per_turn + 2  # a budget big enough for the cap to bind before it
    state.deposits_taken = deposit_limit(budget)

    assert deposit_blocked(state, budget) == "No more deposits this turn."


def test_a_hand_of_plain_wu_has_no_power_to_use(state, settings, card):
    state.player.hand = [card(PLAIN_WU), card(ANOTHER_PLAIN_WU)]
    assert use_power_blocked(state, settings.actions_per_turn) == "No Wu with a usable power."


def test_a_use_power_is_out_of_reach_once_the_action_is_spent(state, settings, card):
    """A `use`-trigger Wu only counts while the turn's action is unspent — say *that*, not "no power"."""
    state.player.hand = [card(BRAS_FINGER), card(PLAIN_WU)]
    state.actions_taken = settings.actions_per_turn

    assert use_power_blocked(state, settings.actions_per_turn) == SPENT_MESSAGE


def test_a_usable_power_has_no_reason(state, settings, card):
    state.player.hand = [card(BRAS_FINGER), card(PLAIN_WU)]
    assert use_power_blocked(state, settings.actions_per_turn) is None


# --- and the vault shows it -----------------------------------------------------


async def test_a_blocked_action_explains_itself_on_hover(state, settings, open_vault, tooltips_in):
    state.actions_taken = settings.actions_per_turn

    async with open_vault(state) as (app, _pilot):
        assert SPENT_MESSAGE in tooltips_in(app, "#actions")


async def test_an_available_action_still_describes_itself(state, open_vault, tooltips_in):
    async with open_vault(state) as (app, _pilot):
        assert "Duel for the next Wu on the pile." in tooltips_in(app, "#actions")
