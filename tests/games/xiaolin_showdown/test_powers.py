"""Every Wu power resolves to a mechanic somebody implemented.

The card DB stores `(trigger, effect)` pairs. A pair with no entry in `RULES` is a Wu whose
power quietly does nothing — the failure that hid Intangibility for the whole life of the game.
"""

from __future__ import annotations

import pytest

from xiaolin_showdown.logic.duel import Round
from xiaolin_showdown.logic.mechanics.powers import (
    RULES,
    UNPRINTED,
    Mechanic,
    Timing,
    is_boost_slot,
    mechanic_of,
    rule_of,
)
from xiaolin_showdown.logic.mechanics.resolve import resolve_played_power
from xiaolin_showdown.logic.models import Power


def test_every_power_in_the_card_db_has_a_mechanic(catalog):
    for power in catalog.powers:
        rule_of(power)  # raises on an unimplemented (trigger, effect) pair


def test_every_mechanic_is_reachable_from_some_power(catalog):
    """A mechanic no card can trigger is code nobody runs — declare it UNPRINTED or delete it."""
    used = {mechanic_of(power) for power in catalog.powers}
    assert used == set(Mechanic) - UNPRINTED


def test_an_unprinted_mechanic_really_has_no_card(catalog):
    """UNPRINTED is a promise, not a shrug: the moment a card uses one, drop it from the set."""
    used = {mechanic_of(power) for power in catalog.powers}
    assert used.isdisjoint(UNPRINTED)


def test_an_unknown_pair_raises_rather_than_doing_nothing():
    invented = Power(99, "Unknown", "play", 7, "")
    with pytest.raises(KeyError, match="no mechanic"):
        rule_of(invented)


@pytest.mark.parametrize("rule", RULES.values(), ids=lambda rule: rule.mechanic.value)
def test_each_mechanic_states_its_rule(rule):
    assert rule.text.endswith(".")
    assert isinstance(rule.timing, Timing)


# --- the in-duel mechanics, resolved through the real card DB --------------------

SILVER_MANTA_RAY = 1  # boost/0, dragon element
MOBY_MORPHER = 5  # play/+1
FIST_OF_TEBIGONG = 6  # play/0, 4/0/0 metal
WUSHU_BRACELET = 14  # boost/+1
TWO_TON_TUNIC = 17  # play/0 with -4 force: a negative Wu
SERPENTS_TAIL = 24  # play/-1, Intangibility


def test_a_plain_wu_contributes_its_printed_stats(card):
    duel = Round()
    resolve_played_power(duel, card(FIST_OF_TEBIGONG), is_player=True, element="metal")
    assert duel.player_queue[0].stats["force"] == 4


def test_a_morpher_turns_every_stat_to_one(card):
    duel = Round()
    resolve_played_power(duel, card(MOBY_MORPHER), is_player=True, element="fire")
    assert list(duel.player_queue[0].stats.values()) == [1, 1, 1]


def test_a_morpher_takes_the_element_its_caster_chose(card):
    duel = Round()
    resolve_played_power(duel, card(MOBY_MORPHER), is_player=True, element="fire")
    assert duel.player_queue[0].element == "fire"


def test_a_negative_wu_mirrors_onto_the_opponent(card):
    duel = Round()
    resolve_played_power(duel, card(TWO_TON_TUNIC), is_player=True, element="metal")
    assert duel.bot_queue[0].stats["force"] == -4


def test_a_negative_wu_is_spent_on_the_casters_side(card):
    duel = Round()
    resolve_played_power(duel, card(TWO_TON_TUNIC), is_player=True, element="metal")
    assert duel.player_queue[0].stats["force"] == 0


def test_a_booster_amplifies_the_card_played_after_it(card):
    duel = Round(player_queue=[card(WUSHU_BRACELET)])  # queued at the power stage
    resolve_played_power(duel, card(FIST_OF_TEBIGONG), is_player=True, element="metal")
    assert duel.player_queue[0].stats["force"] == 1  # the booster took on the stat


def test_a_dragon_wu_is_not_a_booster(card):
    """boost/0 lends its own 1/1/1; only boost/+1 amplifies.

    Asserted on agility, not force: the Fist contributes force only, so an amplified dragon would
    still read force 1 while losing agility — a force assertion cannot tell the two apart.
    """
    duel = Round(player_queue=[card(SILVER_MANTA_RAY)])
    resolve_played_power(duel, card(FIST_OF_TEBIGONG), is_player=True, element="water")
    assert duel.player_queue[0].stats["agility"] == 1  # printed stat kept, not zeroed by boosting


def test_intangibility_voids_the_elemental_bonus(card):
    voided = resolve_played_power(Round(), card(SERPENTS_TAIL), is_player=True, element="metal")
    assert voided


def test_intangibility_voids_it_for_both_duelists(card):
    """Whoever plays it, nobody earns the bonus — it is a condition of the showdown."""
    voided = resolve_played_power(Round(), card(SERPENTS_TAIL), is_player=False, element="metal")
    assert voided


def test_a_showdown_without_intangibility_keeps_the_bonus(card):
    voided = resolve_played_power(Round(), card(FIST_OF_TEBIGONG), is_player=True, element="metal")
    assert not voided


# --- the boost slot: who may be played in addition to a card ----------------------


def test_only_a_boost_trigger_wu_may_take_the_boost_slot(catalog):
    """It is the *slot*, not the mechanic: both the dragon and the amplifier qualify, nothing else."""
    eligible = {mechanic_of(power) for power in catalog.powers if is_boost_slot(power)}

    assert eligible == {Mechanic.DRAGON, Mechanic.BOOST}


def test_a_hand_or_play_wu_is_never_offered_the_boost_slot(catalog):
    rejected = {mechanic_of(power) for power in catalog.powers if not is_boost_slot(power)}

    assert Mechanic.DRAGON not in rejected
    assert Mechanic.BOOST not in rejected
    assert Mechanic.PRINTED_STATS in rejected
