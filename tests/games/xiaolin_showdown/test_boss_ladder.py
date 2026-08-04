"""The boss ladder — bosses earned by winning, not chosen off a menu from the start.

Hard's clear opens Jack; each boss's own clear opens the next (Hannibal < Wuya < Chase). All of it
lives in one number, ``Settings.options["boss_ladder"]`` — these tests are about that number's rules.
"""

from __future__ import annotations

from termcade.core.settings import Difficulty, Settings

from xiaolin_showdown.logic.catalog import load_catalog
from xiaolin_showdown.logic.ladder import (
    boss_tier_unlocked,
    effective_difficulty,
    progress,
    record_win,
    unlocked_bosses,
)

_BOSSES = load_catalog().opponents("boss")
_JACK = next(b for b in _BOSSES if b.name == "Jack_Spicer")
_HANNIBAL = next(b for b in _BOSSES if b.name == "Hannibal_Roy_Bean")
_WUYA = next(b for b in _BOSSES if b.name == "Wuya")
_CHASE = next(b for b in _BOSSES if b.name == "Chase_Young")


def _settings(*, difficulty: Difficulty = Difficulty.EASY, ladder: int = 0) -> Settings:
    return Settings(difficulty=difficulty, options={"boss_ladder": ladder})


def test_fresh_settings_have_a_locked_boss_tier() -> None:
    assert progress(Settings()) == 0
    assert not boss_tier_unlocked(Settings())


def test_beating_hard_opens_the_first_stage() -> None:
    updated = record_win(_settings(difficulty=Difficulty.HARD), difficulty=Difficulty.HARD, boss=None)

    assert progress(updated) == 1


def test_beating_easy_opens_nothing() -> None:
    settings = _settings(difficulty=Difficulty.EASY)
    updated = record_win(settings, difficulty=Difficulty.EASY, boss=None)

    assert updated is settings  # unchanged, not merely equal — a no-op writes nothing


def test_beating_hard_twice_does_not_advance_past_the_first_stage() -> None:
    already_open = _settings(ladder=1)
    updated = record_win(already_open, difficulty=Difficulty.HARD, boss=None)

    assert updated is already_open


def test_beating_jack_at_the_ladders_edge_opens_hannibal() -> None:
    settings = _settings(difficulty=Difficulty.BOSS, ladder=1)
    updated = record_win(settings, difficulty=Difficulty.BOSS, boss=_JACK)

    assert progress(updated) == 2


def test_beating_a_boss_ahead_of_the_ladders_edge_does_not_skip_a_stage() -> None:
    """Hannibal is stage 1 — beating him while still at stage 0 (Jack not yet cleared) should not
    happen through the picker, but the rule itself must refuse to skip ahead if it ever does."""
    settings = _settings(difficulty=Difficulty.BOSS, ladder=0)
    updated = record_win(settings, difficulty=Difficulty.BOSS, boss=_HANNIBAL)

    assert updated is settings


def test_beating_an_already_cleared_boss_does_not_advance_again() -> None:
    settings = _settings(difficulty=Difficulty.BOSS, ladder=2)  # Jack and Hannibal both cleared
    updated = record_win(settings, difficulty=Difficulty.BOSS, boss=_JACK)

    assert updated is settings


def test_clearing_the_whole_ladder_in_order() -> None:
    settings = Settings()
    for boss in (None, _JACK, _HANNIBAL, _WUYA, _CHASE):
        difficulty = Difficulty.HARD if boss is None else Difficulty.BOSS
        settings = record_win(settings, difficulty=difficulty, boss=boss)

    assert unlocked_bosses(_BOSSES, settings) == [_JACK, _HANNIBAL, _WUYA, _CHASE]


def test_unlocked_bosses_is_empty_before_hard_is_beaten() -> None:
    assert unlocked_bosses(_BOSSES, _settings(ladder=0)) == []


def test_unlocked_bosses_follows_ladder_order() -> None:
    assert unlocked_bosses(_BOSSES, _settings(ladder=2)) == [_JACK, _HANNIBAL]


def test_effective_difficulty_folds_a_locked_boss_setting_to_hard() -> None:
    """A settings file that predates the ladder (or was hand-edited) may still say ``boss`` with no
    progress behind it — that must play as Hard, not hand the picker an empty roster."""
    stale = _settings(difficulty=Difficulty.BOSS, ladder=0)

    assert effective_difficulty(stale) is Difficulty.HARD


def test_effective_difficulty_honours_boss_once_unlocked() -> None:
    unlocked = _settings(difficulty=Difficulty.BOSS, ladder=1)

    assert effective_difficulty(unlocked) is Difficulty.BOSS
