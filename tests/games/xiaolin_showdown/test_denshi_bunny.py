"""Denshi Bunny — vs a robot construct, a stand-in loses outright; a modifier is nullified instead.
Mala Mala Jong is immune."""

from __future__ import annotations

from termcade.core.rng import Rng

from factories import auto_choices, wu

from xiaolin_showdown.logic import jack
from xiaolin_showdown.logic.battle import Round
from xiaolin_showdown.logic.catalog import load_catalog
from xiaolin_showdown.logic.duel import Duel
from xiaolin_showdown.logic.setup import new_game


def _jack_duel() -> Duel:
    cat = load_catalog()
    jack_char = next(c for c in cat.characters if c.name == "Jack_Spicer")
    state = new_game(cat, Rng(1), cat.character(1), opponent=jack_char)
    duel = Duel(state, Rng(1), auto_choices())
    duel.duel.rounds = [Round(stat="")]
    return duel


def test_hack_auto_wins_against_ai_jack():
    duel = _jack_duel()
    duel.duel.jack_mode = jack.AI_JACK_NAME
    duel._hack_construct(True)
    assert duel.duel.auto_winner is True


def test_hack_auto_wins_against_attack():
    duel = _jack_duel()
    duel.duel.jack_mode = jack.ATTACK_NAME
    duel._hack_construct(True)
    assert duel.duel.auto_winner is True


def test_hack_nullifies_chamelon_bots_boost_not_an_auto_win():
    duel = _jack_duel()
    duel.duel.jack_mode = jack.CHAMELON_NAME
    chamelon_boost = wu(2, 2, 2, name="Chamelon-Bot")
    duel.duel.round.bot.queue.append(chamelon_boost)
    duel.duel.round.bot.jack_bot.append(chamelon_boost)
    duel._hack_construct(True)
    assert duel.duel.auto_winner is None
    assert chamelon_boost.stats == {"force": 0, "agility": 0, "intellect": 0}


def test_hack_leaves_a_real_boost_untouched_against_chamelon():
    """Jack's boost slot can hold a real Wu instead of Chamelon-Bot's synthetic card (it competes
    for the slot) — only the tracked Chamelon-Bot card may be nullified, never a genuine boost."""
    duel = _jack_duel()
    duel.duel.jack_mode = jack.CHAMELON_NAME
    real_boost = wu(3, 3, 3, name="Two-Ton Tunic")
    duel.duel.round.bot.queue.append(real_boost)
    duel._hack_construct(True)
    assert real_boost.stats == {"force": 3, "agility": 3, "intellect": 3}


def test_hack_nullifies_jack_bots_curse_when_he_fights_as_himself():
    duel = _jack_duel()
    duel.duel.jack_mode = None
    curse_mirror = wu(-1, -1, -1, name="Tickle-Bot")
    duel.duel.round.player.queue.append(curse_mirror)
    duel.duel.round.player.suffered.append(curse_mirror)
    duel.duel.round.player.jack_bot.append(curse_mirror)
    duel._hack_construct(True)
    assert duel.duel.auto_winner is None
    assert curse_mirror.stats == {"force": 0, "agility": 0, "intellect": 0}


def test_hack_leaves_other_curses_on_the_side_untouched():
    """A different curse source landing the same battle must survive — only Jack-Bot's own mirror,
    tracked via `jack_bot`, is nullified."""
    duel = _jack_duel()
    duel.duel.jack_mode = None
    other_curse = wu(-1, -1, -1, name="Some Other Curse")
    duel.duel.round.player.queue.append(other_curse)
    duel.duel.round.player.suffered.append(other_curse)
    duel._hack_construct(True)
    assert other_curse.stats == {"force": -1, "agility": -1, "intellect": -1}


def test_hack_does_nothing_against_mala_mala_jong():
    duel = _jack_duel()
    duel.duel.jack_mode = None
    duel.state.bot.jong_form = True
    curse_mirror = wu(-1, -1, -1, name="Tickle-Bot")
    duel.duel.round.player.jack_bot.append(curse_mirror)
    duel._hack_construct(True)
    assert duel.duel.auto_winner is None
    assert curse_mirror.stats == {"force": -1, "agility": -1, "intellect": -1}


def test_hack_does_nothing_against_a_non_jack_opponent():
    cat = load_catalog()
    hannibal = next(c for c in cat.characters if "Hannibal" in c.name)
    state = new_game(cat, Rng(1), cat.character(1), opponent=hannibal)
    duel = Duel(state, Rng(1), auto_choices())
    duel.duel.rounds = [Round(stat="")]
    curse_mirror = wu(-1, -1, -1, name="Tickle-Bot")
    duel.duel.round.player.jack_bot.append(curse_mirror)
    duel._hack_construct(True)
    assert duel.duel.auto_winner is None
    assert curse_mirror.stats == {"force": -1, "agility": -1, "intellect": -1}
