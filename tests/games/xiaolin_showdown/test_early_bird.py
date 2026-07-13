"""The Early Bird Gets The Worm — a Wu taken by being faster, instead of by winning a showdown.

Outrun the other duelist on initiative by ``early_bird_gap`` and the next Wu off the pile is yours
with no duel. You were simply quicker: you reached it first, so there was nothing to fight over.

The price is what makes it a rule rather than a gift. You surrender one of your **fastest** Wu — by
magnitude, so a ``-2`` costs as much as a ``+2`` — and it is discarded for no points. The lead that
bought the worm is the lead you spend on it, so nobody flies twice on the same wings.

Both duelists play by this, and the numbers are read off the settings, never restated.
"""

from __future__ import annotations

from itertools import combinations_with_replacement

import pytest

from xiaolin_showdown.logic.actions import (
    can_early_bird,
    early_bird,
    early_bird_blocked,
    early_bird_options,
    initiative_lead,
)
from xiaolin_showdown.logic.mechanics.cards import is_one_of
from xiaolin_showdown.logic.mechanics.scoring import initiative
from xiaolin_showdown.logic.settings import XiaolinSettings
from xiaolin_showdown.logic.turn import duel_value
from xiaolin_showdown.logic.vault_ai import choose_early_bird

# Read by property, never by id — the pool is rebalanced constantly and these must survive it.


def _by_bonus(catalog, wanted):
    """A fresh Wu whose initiative bonus is exactly ``wanted``."""
    from copy import deepcopy

    for card in catalog.cards:
        if card.power.initiative_bonus == wanted:
            return deepcopy(card)
    pytest.skip(f"no Wu prints an initiative bonus of {wanted:+d}")


def _plain(catalog):
    """A fresh Wu with no initiative at all — it can never be the Early Bird's price."""
    from copy import deepcopy

    for card in catalog.cards:
        if not card.power.initiative_bonus and card.id >= 5:
            return deepcopy(card)
    raise AssertionError("the pool prints no Wu without initiative")


def _outrun(state, catalog):
    """Give the player a lead of exactly the gap: distinct bonuses stack, equal ones do not."""
    settings = XiaolinSettings()
    state.player.hand = [_by_bonus(catalog, 1), _by_bonus(catalog, 2), _plain(catalog)]
    state.bot.hand = [_plain(catalog)]
    assert initiative_lead(state, is_player=True) >= settings.early_bird_gap
    return settings


def test_a_lead_of_the_gap_opens_the_early_bird(state, catalog):
    settings = _outrun(state, catalog)

    assert can_early_bird(state, settings)


def test_a_lead_below_the_gap_does_not(state, catalog):
    """The gap is the whole rule — one short of it is no lead at all."""
    settings = XiaolinSettings()
    state.player.hand = [_by_bonus(catalog, 1), _plain(catalog)]  # a lead of 1
    state.bot.hand = [_plain(catalog)]

    assert initiative_lead(state, is_player=True) < settings.early_bird_gap
    assert not can_early_bird(state, settings)
    assert early_bird_blocked(state, settings)  # and it says why


def test_equal_bonuses_do_not_stack_into_a_lead(state, catalog):
    """Two `+1` Wu are one `+1`. The gap is reachable only by collecting *different* speeds."""
    settings = XiaolinSettings()
    state.player.hand = [_by_bonus(catalog, 1), _by_bonus(catalog, 1), _by_bonus(catalog, 1)]
    state.bot.hand = [_plain(catalog)]

    assert initiative_lead(state, is_player=True) < settings.early_bird_gap
    assert not can_early_bird(state, settings)


def test_the_drag_you_hold_is_a_lead_you_gain(state, catalog):
    """A `-2` lands on the *opponent* — so slowing them is another way of being faster.

    That is why the Early Bird's price is read by magnitude: the `-2` in your hand is doing the same
    work as a `+2`, and giving it up costs you the same two points of lead.
    """
    state.player.hand = [_by_bonus(catalog, 1), _by_bonus(catalog, -2), _plain(catalog)]
    state.bot.hand = [_plain(catalog)]

    _, bot_side = initiative(state.player, state.bot)

    assert bot_side < 0  # the drag landed on THEM — that is the whole rule
    assert can_early_bird(state, XiaolinSettings())  # and it opened the Early Bird


def test_the_price_is_your_fastest_wu(state, catalog):
    """Not any Wu of speed — the *highest*, so it costs you the thing you outran them with."""
    _outrun(state, catalog)
    options = early_bird_options(state)

    top = max(abs(c.power.initiative_bonus) for c in state.player.hand if c.power.initiative_bonus)

    assert options and all(abs(card.power.initiative_bonus) == top for card in options)


def test_a_drag_is_as_fast_as_a_lift(state, catalog):
    """Magnitude, not sign: a `-2` you hold is as much a Wu of speed as a `+2`, and costs the same.

    The `-2` is the *fastest* Wu in this hand even though it is the lowest number in it, so it — and
    not the `+1` — is what the Early Bird asks for.
    """
    drag, lift = _by_bonus(catalog, -2), _by_bonus(catalog, 1)
    state.player.hand = [drag, lift, _plain(catalog)]
    state.bot.hand = [_plain(catalog)]

    options = early_bird_options(state)

    assert is_one_of(drag, options)
    assert not is_one_of(lift, options)


def test_the_worm_is_the_next_wu_on_the_pile(state, catalog):
    """The very Wu the next showdown would have been fought over — taken without fighting it."""
    _outrun(state, catalog)
    worm = state.card_deck[0]
    pile_before = len(state.card_deck)

    early_bird(state, early_bird_options(state)[0])

    assert is_one_of(worm, state.player.hand)
    assert len(state.card_deck) == pile_before - 1  # off the top of the pile, not out of nowhere


def test_the_surrendered_wu_is_discarded_not_banked(state, catalog):
    """It is spent, like any power: no points, and it does not go to the shelf."""
    _outrun(state, catalog)
    price = early_bird_options(state)[0]
    before = state.player.points

    early_bird(state, price)

    assert not is_one_of(price, state.player.hand)
    assert not is_one_of(price, state.player.deck)
    assert state.player.points == before


def test_flying_costs_the_turns_action(state, catalog):
    _outrun(state, catalog)

    early_bird(state, early_bird_options(state)[0])

    assert state.actions_taken == 1


def test_the_lead_that_bought_it_is_spent_on_it(state, catalog):
    """You cannot fly twice on the same wings: the price is taken out of the very lead that paid."""
    settings = _outrun(state, catalog)
    before = initiative_lead(state, is_player=True)

    early_bird(state, early_bird_options(state)[0])

    assert initiative_lead(state, is_player=True) < before
    assert not can_early_bird(state, settings)  # the worm cost the wings


def test_an_empty_pile_leaves_no_worm(state, catalog):
    settings = _outrun(state, catalog)
    state.card_deck.clear()

    assert not can_early_bird(state, settings)


def test_taking_the_last_wu_ends_the_run(state, catalog):
    """The pile is the clock. Emptying it ends the run, however it was emptied."""
    _outrun(state, catalog)
    state.card_deck[:] = state.card_deck[:1]

    early_bird(state, early_bird_options(state)[0])

    assert state.has_ended


def test_the_opponent_flies_by_the_same_rule(state, catalog):
    """Same rule both sides — it takes off the shared pile, and it pays the same price."""
    state.bot.hand = [_by_bonus(catalog, 1), _by_bonus(catalog, 2), _plain(catalog)]
    state.player.hand = [_plain(catalog)]
    worm = state.card_deck[0]
    price = early_bird_options(state, is_player=False)[0]

    early_bird(state, price, is_player=False)

    assert is_one_of(worm, state.bot.hand)
    assert not is_one_of(price, state.bot.hand)
    assert state.bot_actions_taken == 1
    assert state.actions_taken == 0  # the player's own turn is untouched


def test_a_spent_turn_grounds_the_bird(state, catalog):
    """One action a turn, and this is one — it queues behind a deposit like everything else."""
    settings = _outrun(state, catalog)
    state.actions_taken = settings.actions_per_turn

    assert not can_early_bird(state, settings)


def test_you_can_never_outrun_them_on_a_wu_you_do_not_hold(state, catalog):
    """A lead always comes out of your *own* hand — so the price can always be paid.

    Worth pinning, because it is easy to assume the opposite. Their negatives do not slow *them*: they
    land on **you** (`scoring.initiative`). Your lead is your own positives, plus your own negatives
    dragging them down — both of which are Wu in your hand. So "fast enough to fly, with nothing to
    surrender" cannot happen, and `early_bird_blocked`'s guard against it is belt-and-braces.

    Swept over every hand the pool can print, rather than argued.
    """
    settings = XiaolinSettings()
    bonuses = sorted({c.power.initiative_bonus for c in catalog.cards if c.power.initiative_bonus})

    for mine in combinations_with_replacement([0, *bonuses], 3):
        for theirs in combinations_with_replacement([0, *bonuses], 3):
            state.player.hand = [_by_bonus(catalog, b) if b else _plain(catalog) for b in mine]
            state.bot.hand = [_by_bonus(catalog, b) if b else _plain(catalog) for b in theirs]

            if initiative_lead(state, is_player=True) >= settings.early_bird_gap:
                assert early_bird_options(state), (
                    f"a lead of {initiative_lead(state, is_player=True)} with nothing to pay it with: "
                    f"mine={mine} theirs={theirs}"
                )


async def test_the_power_screen_offers_it_only_to_a_duelist_who_is_fast_enough(open_vault, state, catalog):
    """Through the real screen: the button is there, or it is not.

    Worth driving the UI rather than the rule — a screen that raises inside a Textual worker fails
    *silently*, and this one is reached by a key press nothing else covers.
    """
    state.player.hand = [_plain(catalog)]
    state.bot.hand = [_plain(catalog)]

    async with open_vault(state) as (app, pilot):
        await pilot.press("4")  # Use a Power
        await pilot.pause()
        assert not app.screen.query("#early-bird")  # too slow — the power is not on offer


async def test_flying_it_from_the_power_screen_takes_the_wu(open_vault, state, catalog):
    """The whole path a player walks: Use a Power → the Early Bird → pick what to give up."""
    _outrun(state, catalog)
    worm = state.card_deck[0]

    async with open_vault(state) as (app, pilot):
        await pilot.press("4")  # Use a Power
        await pilot.pause()
        assert app.screen.query("#early-bird")  # fast enough — it is listed with the Wu powers

        await pilot.click("#early-bird")
        await pilot.pause()
        await pilot.click("#opt-0")  # surrender the first of the Wu tied at the top
        await pilot.pause()

    assert is_one_of(worm, state.player.hand)
    assert state.actions_taken == 1


# --- the opponent's policy: when it is worth flying at all ---------------------------------------
#
# The rule above says a duelist *may* fly. This says when the opponent *does* — and it is the half that
# went untested while the simulation was busy measuring it. Flying costs a real Wu, the lead that names
# the challenge, and the turn's action (which could have banked points, and points are the win
# condition). Measured, an opponent that flew whenever it could lost ~8 points of win rate. So it flies
# as a comeback: only while it is behind.


def _bot_outruns(state, catalog):
    """Put the opponent three ahead on initiative, holding a Wu it could afford to give up."""
    state.bot.hand = [_by_bonus(catalog, 1), _by_bonus(catalog, 2), _plain(catalog)]
    state.player.hand = [_plain(catalog)]
    settings = XiaolinSettings()
    assert initiative_lead(state, is_player=False) >= settings.early_bird_gap
    return settings


def test_the_opponent_flies_it_when_it_is_behind(state, catalog):
    """A duelist who is losing has nothing to protect. A fresh Wu is the fastest way back in."""
    settings = _bot_outruns(state, catalog)
    state.bot.points, state.player.points = 3, 9

    assert choose_early_bird(state, settings) is not None


def test_the_opponent_refuses_it_while_it_is_ahead(state, catalog):
    """Ahead, the trade is bad: it would spend the lead that names every challenge, and an action that
    could have banked the points it is winning with."""
    settings = _bot_outruns(state, catalog)
    state.bot.points, state.player.points = 9, 3

    assert choose_early_bird(state, settings) is None


def test_level_on_points_is_not_behind(state, catalog):
    """The rule is *behind*, not *not ahead* — a dead heat is no reason to give a Wu away."""
    settings = _bot_outruns(state, catalog)
    state.bot.points = state.player.points = 5

    assert choose_early_bird(state, settings) is None


def test_the_opponent_gives_up_the_cheapest_of_the_wu_tied_at_the_top(state, catalog):
    """They all cost the same speed, so it lets go of the one that fights worst."""
    settings = _bot_outruns(state, catalog)
    state.bot.points, state.player.points = 1, 9

    # two Wu tied for fastest, one worth more in a battle than the other
    fast, faster = _by_bonus(catalog, 2), _by_bonus(catalog, -2)
    state.bot.hand = [_by_bonus(catalog, 1), fast, faster]
    cheaper = min((fast, faster), key=duel_value)

    assert choose_early_bird(state, settings) is cheaper


def test_the_opponent_does_not_fly_on_a_spent_turn(state, catalog):
    """One action a turn, and this is one — the opponent is held to the rule the player is."""
    settings = _bot_outruns(state, catalog)
    state.bot.points, state.player.points = 1, 9
    state.bot_actions_taken = settings.actions_per_turn

    assert choose_early_bird(state, settings) is None


def test_the_opponent_does_not_fly_at_an_empty_pile(state, catalog):
    """There is nothing to reach first."""
    settings = _bot_outruns(state, catalog)
    state.bot.points, state.player.points = 1, 9
    state.card_deck.clear()

    assert choose_early_bird(state, settings) is None


def test_the_opponent_does_not_fly_without_the_lead(state, catalog):
    """The gap is the price of the Wu, for the opponent exactly as for the player."""
    settings = XiaolinSettings()
    state.bot.hand = [_by_bonus(catalog, 1), _plain(catalog)]  # a lead of 1, not the gap
    state.player.hand = [_plain(catalog)]
    state.bot.points, state.player.points = 1, 9

    assert initiative_lead(state, is_player=False) < settings.early_bird_gap
    assert choose_early_bird(state, settings) is None
