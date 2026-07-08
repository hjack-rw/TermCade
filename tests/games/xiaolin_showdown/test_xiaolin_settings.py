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
