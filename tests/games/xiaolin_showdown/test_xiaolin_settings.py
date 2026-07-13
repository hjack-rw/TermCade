"""XiaolinSettings.coerce — clamps out-of-range rules and reports every value it had to change."""

from __future__ import annotations

from dataclasses import asdict

from xiaolin_showdown.logic.settings import XiaolinSettings


def _defaults() -> dict[str, int]:
    return asdict(XiaolinSettings())


def test_coerce_accepts_valid_settings_with_an_empty_report() -> None:
    _, adjusted = XiaolinSettings.coerce(_defaults())
    assert adjusted == {}


def test_coerce_flags_a_max_hand_below_the_starting_hand() -> None:
    values = _defaults() | {"max_hand_size": 4}  # the starting hand is 5, so a cap of 4 is nonsensical
    _, adjusted = XiaolinSettings.coerce(values)
    assert adjusted["max_hand_size"] == (4, 5)


def test_coerce_raises_the_max_hand_to_cover_the_starting_hand() -> None:
    values = _defaults() | {"max_hand_size": 4}
    coerced, _ = XiaolinSettings.coerce(values)
    assert coerced.max_hand_size == 5


def test_the_mercy_hand_can_never_beat_the_wager_cap():
    """Being dealt back in must not pay better than playing well.

    The mercy rule is income, and it is paid to whoever is losing — a hand empties because it was
    staked and forfeited. Unclamped, raising this one number in the Settings box took the player's
    hard-tier win rate from 37% to 72%: you were simply paid more for losing. You are dealt back in to
    duel, never dealt more than you could have staked.
    """
    greedy = XiaolinSettings(empty_draw_limit=9, max_wager=3)

    assert greedy.empty_draw_limit == greedy.max_wager


def test_the_mercy_hand_follows_the_wager_cap_up_as_well_as_down():
    """It is a cap, not a constant: raise what may be staked and the mercy rises with it."""
    generous = XiaolinSettings(empty_draw_limit=5, max_wager=5)

    assert generous.empty_draw_limit == 5


def test_a_mercy_hand_below_the_cap_is_left_alone():
    """The clamp only ever takes away. A deliberately meagre mercy stays meagre."""
    lean = XiaolinSettings(empty_draw_limit=1, max_wager=3)

    assert lean.empty_draw_limit == 1
