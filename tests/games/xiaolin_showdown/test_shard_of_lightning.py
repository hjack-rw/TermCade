"""Shard of Lightning — +1 to the contested stat per metal Wu on the table this battle, -1 per
non-metal one, either side, boosts and inert curse mirrors alike. The arena counts the same way.
Can go negative. Uncapped either way."""

from __future__ import annotations

from termcade.core.rng import Rng

from factories import auto_choices, wu

from xiaolin_showdown.logic.flow.battle import Round
from xiaolin_showdown.logic.schema.catalog import load_catalog
from xiaolin_showdown.logic.flow.duel import Duel
from xiaolin_showdown.logic.flow.setup import new_game


def _duel(*, stat: str = "force", background: str = "") -> Duel:
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1), opponent=cat.character(2))
    duel = Duel(state, Rng(1), auto_choices())
    duel.duel.background = background
    duel.duel.rounds = [Round(stat=stat)]
    return duel


def test_bonus_is_zero_when_nobody_cast_it_this_round():
    duel = _duel()
    assert duel._conduct_bonus(True) == 0
    assert duel._conduct_bonus(False) == 0


def test_own_copy_counts_toward_its_own_bonus():
    duel = _duel()
    duel.duel.round.conduct_caster = True
    duel.duel.round.player.queue.append(wu(0, 0, 0, name="Shard of Lightning"))
    assert duel._conduct_bonus(True) == 1


def test_metal_background_adds_one_more():
    duel = _duel(background="metal")
    duel.duel.round.conduct_caster = True
    duel.duel.round.player.queue.append(wu(0, 0, 0, name="Shard of Lightning"))
    assert duel._conduct_bonus(True) == 2


def test_non_metal_background_subtracts_one():
    duel = _duel(background="water")
    duel.duel.round.conduct_caster = True
    duel.duel.round.player.queue.append(wu(0, 0, 0, name="Shard of Lightning"))
    assert duel._conduct_bonus(True) == 0


def test_an_undecided_background_contributes_nothing():
    duel = _duel(background="")
    duel.duel.round.conduct_caster = True
    duel.duel.round.player.queue.append(wu(0, 0, 0, name="Shard of Lightning"))
    assert duel._conduct_bonus(True) == 1


def test_nets_metal_and_non_metal_wu_on_both_sides_including_boosts():
    duel = _duel()
    duel.duel.round.conduct_caster = True
    duel.duel.round.player.queue.append(wu(0, 0, 0, name="Shard of Lightning"))  # metal, +1
    duel.duel.round.player.queue.append(wu(1, 1, 1, name="Own Boost"))  # metal, +1
    duel.duel.round.bot.queue.append(wu(2, 0, 0, name="Their Wu"))  # metal, +1
    duel.duel.round.bot.queue.append(wu(0, 2, 0, element="fire", name="Non-Metal Wu"))  # -1
    assert duel._conduct_bonus(True) == 2


def test_can_go_negative_in_a_non_metal_heavy_field():
    duel = _duel(background="water")
    duel.duel.round.conduct_caster = True
    duel.duel.round.player.queue.append(wu(0, 0, 0, name="Shard of Lightning"))  # metal, +1
    duel.duel.round.bot.queue.append(wu(0, 0, 3, element="water", name="A"))
    duel.duel.round.bot.queue.append(wu(0, 0, 3, element="fire", name="B"))
    assert duel._conduct_bonus(True) == -2


def test_an_elementless_card_counts_as_neither():
    """Chamelon-Bot's synthetic denial bump is deliberately elementless — it must not read as a
    non-metal penalty, the way the arena treats "no element" as standing outside it."""
    duel = _duel()
    duel.duel.round.conduct_caster = True
    duel.duel.round.player.queue.append(wu(0, 0, 0, name="Shard of Lightning"))
    duel.duel.round.bot.queue.append(wu(0, 0, 1, element="", name="Elementless"))
    assert duel._conduct_bonus(True) == 1


def test_an_inert_curse_mirror_still_counts():
    """A Jack-Bot curse mirror is stats-zeroed but keeps its metal element — it still reads as
    metal on the table for Shard of Lightning."""
    duel = _duel()
    duel.duel.round.conduct_caster = True
    duel.duel.round.player.queue.append(wu(0, 0, 0, name="Shard of Lightning"))
    mirror = wu(0, 0, 0, name="Tickle-Bot")
    duel.duel.round.player.queue.append(mirror)
    assert duel._conduct_bonus(True) == 2


def test_bonus_does_not_apply_to_the_non_caster_side():
    duel = _duel()
    duel.duel.round.conduct_caster = True
    duel.duel.round.player.queue.append(wu(0, 0, 0, name="Shard of Lightning"))
    assert duel._conduct_bonus(False) == 0


def test_player_base_adds_the_bonus_only_on_the_contested_stat():
    duel = _duel(stat="force")
    before = dict(duel._player_base())
    duel.duel.round.conduct_caster = True
    duel.duel.round.player.queue.append(wu(0, 0, 0, name="Shard of Lightning"))
    after = duel._player_base()
    assert after["force"] == before["force"] + 1
    assert after["agility"] == before["agility"]
    assert after["intellect"] == before["intellect"]


def test_bot_base_adds_the_bonus_when_the_bot_is_the_caster():
    duel = _duel(stat="agility")
    before = dict(duel._bot_base())
    duel.duel.round.conduct_caster = False
    duel.duel.round.bot.queue.append(wu(0, 0, 0, name="Shard of Lightning"))
    after = duel._bot_base()
    assert after["agility"] == before["agility"] + 1
