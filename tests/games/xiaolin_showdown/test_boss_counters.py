"""A boss wary of its own counters — steal them, and bank them the instant they're held.

Jack's own five (see logic/jack.py), Hannibal's own five, and Chase's one (all in
docs/design/BOSSES.md) are the keyed sets built so far; Wuya has none yet, and that is a real,
empty set, not a gap."""

from __future__ import annotations

from termcade.core.rng import Rng

from factories import duelist, wu

from xiaolin_showdown.logic import bot, jack
from xiaolin_showdown.logic.mechanics.powers import Mechanic
from xiaolin_showdown.logic.models import Character, Power
from xiaolin_showdown.logic.turn import _priority_deposit, counters_against, pick_deposit


def _character(name: str, mechanic: Mechanic) -> Character:
    return Character(0, name, dict.fromkeys(("force", "agility", "intellect"), 3), Power(0, "", mechanic, ""), "heylin", False)


def _jack_character() -> Character:
    return _character("Jack_Spicer", Mechanic.BOT)


def _hannibal_character() -> Character:
    return _character("Hannibal_Roy_Bean", Mechanic.MORPH)


def _chase_character() -> Character:
    return _character("Chase_Young", Mechanic.BEAST_FORM)


def _plain_character() -> Character:
    return _character("Wuya", Mechanic.WITCHCRAFT)


def test_counters_against_jack_is_his_own_set():
    assert counters_against(_jack_character()) == jack.COUNTER_MECHANICS


def test_counters_against_hannibal_is_his_five():
    counters = counters_against(_hannibal_character())
    assert counters == frozenset(
        {
            Mechanic.NULLIFY_BOOST,
            Mechanic.REVERSE_ELEMENT,
            Mechanic.CLEANSE,
            Mechanic.SET_ELEMENT,
            Mechanic.SET_ARENA,
        }
    )


def test_counters_against_chase_is_nullify_stats():
    assert counters_against(_chase_character()) == frozenset({Mechanic.NULLIFY_STATS})


def test_counters_against_a_boss_with_none_is_empty():
    assert counters_against(_plain_character()) == frozenset()


def test_steal_target_prefers_a_counter_over_a_stronger_ordinary_card():
    weak_counter = wu(0, name="Denshi Bunny", mechanic=Mechanic.HACK, points=4)
    strong_ordinary = wu(5, name="Strong", points=3)
    target = bot.steal_target(
        [strong_ordinary, weak_counter], [], Rng(1), prefer=jack.is_counter
    )
    assert target is weak_counter


def test_steal_target_without_prefer_ranks_the_whole_hand():
    weak_counter = wu(0, name="Denshi Bunny", mechanic=Mechanic.HACK, points=4)
    strong_ordinary = wu(5, name="Strong", points=3)
    target = bot.steal_target([strong_ordinary, weak_counter], [], Rng(1))
    assert target is strong_ordinary


def test_priority_deposit_picks_jacks_own_counter():
    player = duelist(name="Jack_Spicer")
    player.character = _jack_character()
    counter = wu(1, name="Sands of Time", mechanic=Mechanic.STEAL, points=5)
    ordinary = wu(5, name="Strong", points=8)
    player.hand = [ordinary, counter]
    assert _priority_deposit(player) is counter


def test_priority_deposit_is_none_without_a_counter_in_hand():
    player = duelist(name="Jack_Spicer")
    player.character = _jack_character()
    player.hand = [wu(5, name="Strong", points=8)]
    assert _priority_deposit(player) is None


def test_priority_deposit_picks_chases_counter():
    player = duelist(name="Chase_Young")
    player.character = _chase_character()
    counter = wu(0, name="Sphere of Jianyu", mechanic=Mechanic.NULLIFY_STATS, points=4)
    ordinary = wu(5, name="Strong", points=8)
    player.hand = [ordinary, counter]
    assert _priority_deposit(player) is counter


def test_priority_deposit_is_none_for_a_boss_with_no_counter_set():
    player = duelist(name="Wuya")
    player.character = _plain_character()
    player.hand = [wu(0, name="Denshi Bunny", mechanic=Mechanic.HACK, points=4)]
    assert _priority_deposit(player) is None


def test_priority_deposit_falls_back_to_pick_deposit_when_no_counter_held():
    from termcade.core.settings import Difficulty

    player = duelist(name="Jack_Spicer")
    player.character = _jack_character()
    ordinary = wu(5, name="Strong", points=8)
    player.hand = [ordinary]
    assert _priority_deposit(player) is None
    assert pick_deposit(player.hand, Difficulty.BOSS) is ordinary
