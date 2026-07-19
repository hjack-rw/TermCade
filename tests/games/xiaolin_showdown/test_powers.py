"""Every Wu power resolves to a mechanic somebody implemented.

The card DB stores `(trigger, effect)` pairs. A pair with no entry in `RULES` is a Wu whose
power quietly does nothing — the failure that hid Intangibility for the whole life of the game.
"""

from __future__ import annotations

import pytest

from xiaolin_showdown.logic.battle import Round, Side
from xiaolin_showdown.logic.constants import FIRST_DECK_CARD
from xiaolin_showdown.logic.mechanics.powers import (
    MORPH_ASIDE,
    MORPH_CONTESTED,
    RULES,
    UNPRINTED,
    Mechanic,
    Timing,
    is_boost_slot,
    mechanic_of,
    rule_of,
    trigger_of,
)
from xiaolin_showdown.logic.mechanics.resolve import as_boost, resolve_played_power
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


def test_a_mechanic_nobody_implemented_raises_rather_than_doing_nothing(monkeypatch):
    """A named mechanic with no rule behind it is a Wu that quietly does nothing. It must shout.

    A *bad name* can no longer reach this: `Mechanic(row)` rejects it when the DB is loaded. What is
    left is a mechanic somebody added to the enum and never wrote a rule for — so that is what this
    simulates, by taking one out of the table.
    """
    orphan = Power(99, "Unwritten", Mechanic.SUBJUGATION, "")
    monkeypatch.delitem(RULES, Mechanic.SUBJUGATION)

    with pytest.raises(KeyError, match="nobody implemented it"):
        rule_of(orphan)


def test_the_db_refuses_a_mechanic_nobody_named():
    """The failure the whole encoding exists for: a typo is a DB that will not open.

    Under the old `(trigger, effect)` pair a wrong integer was a Wu that silently did nothing for a
    whole run. A wrong *name* cannot survive being read.
    """
    with pytest.raises(ValueError):
        Mechanic("subjuggation")  # a typo, and it never becomes a card


@pytest.mark.parametrize("rule", RULES.values(), ids=lambda rule: rule.mechanic.value)
def test_each_mechanic_states_its_rule(rule):
    assert rule.text.endswith(".")
    assert isinstance(rule.timing, Timing)


# --- the in-duel mechanics, resolved through the real card DB --------------------

SILVER_MANTA_RAY = 1  # boost/0, dragon element
MOBY_MORPHER = 5  # play/+1
FIST_OF_TEBIGONG = 6  # a plain Wu — its stats ARE its power
WUSHU_BRACELET = 14  # boost/+1
TWO_TON_TUNIC = 17  # a plain Wu with negative force: a curse
SERPENTS_TAIL = 24  # play/-1, Intangibility


def test_a_plain_wu_contributes_its_printed_stats(card):
    """Whatever it prints — the rule is *printed*, so the card is asked, never assumed."""
    duel = Round()
    fist = card(FIST_OF_TEBIGONG)

    resolve_played_power(duel, fist, is_player=True, element="metal")

    assert duel.player.queue[0].stats["force"] == fist.stats["force"]


def test_a_morpher_is_worth_less_on_the_stat_the_battle_contests(card):
    duel = Round(stat="agility")
    resolve_played_power(duel, card(MOBY_MORPHER), is_player=True, element="fire")

    stats = duel.player.queue[0].stats
    assert stats["agility"] == MORPH_CONTESTED
    assert stats["force"] == stats["intellect"] == MORPH_ASIDE


def test_the_morphers_dip_follows_whichever_stat_is_contested(card):
    """The shape is not printed on the card — it is cut to the battle it is played into."""
    duel = Round(stat="intellect")
    resolve_played_power(duel, card(MOBY_MORPHER), is_player=True, element="fire")

    assert duel.player.queue[0].stats["intellect"] == MORPH_CONTESTED


def test_a_morpher_takes_the_element_its_caster_chose(card):
    duel = Round(stat="force")
    resolve_played_power(duel, card(MOBY_MORPHER), is_player=True, element="fire")
    assert duel.player.queue[0].element == "fire"


def test_a_negative_wu_mirrors_onto_the_opponent(card):
    duel = Round()
    tunic = card(TWO_TON_TUNIC)

    resolve_played_power(duel, tunic, is_player=True, element="metal")

    assert duel.bot.queue[0].stats["force"] == tunic.stats["force"]  # the wound, entire


def test_a_negative_wu_is_spent_on_the_casters_side(card):
    duel = Round()
    resolve_played_power(duel, card(TWO_TON_TUNIC), is_player=True, element="metal")
    assert duel.player.queue[0].stats["force"] == 0


def test_a_booster_amplifies_the_card_played_after_it(card):
    duel = Round(player=Side(queue=[card(WUSHU_BRACELET)]))  # queued at the power stage
    resolve_played_power(duel, card(FIST_OF_TEBIGONG), is_player=True, element="metal")
    assert duel.player.queue[0].stats["force"] == 1  # the booster took on the stat


def test_a_dragon_wu_is_not_a_booster(card):
    """boost/0 lends its own 1/1/1; only boost/+1 amplifies.

    Asserted on agility, not force: the Fist contributes force only, so an amplified dragon would
    still read force 1 while losing agility — a force assertion cannot tell the two apart.
    """
    duel = Round(player=Side(queue=[card(SILVER_MANTA_RAY)]))
    resolve_played_power(duel, card(FIST_OF_TEBIGONG), is_player=True, element="water")
    assert duel.player.queue[0].stats["agility"] == 1  # printed stat kept, not zeroed by boosting


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


def test_only_boost_slot_wu_may_take_the_boost_slot(catalog):
    """The dragon and the amplifier trigger on "boost"; the Morpher is dual-mode and may also boost."""
    eligible = {mechanic_of(power) for power in catalog.powers if is_boost_slot(power)}

    assert eligible == {Mechanic.DRAGON, Mechanic.BOOST, Mechanic.MORPH}


def test_a_morpher_spent_as_a_boost_is_one_one_one_of_its_chosen_element(catalog):
    """The wudai mode: a flat 1/1/1 in the colour the caster names — a dragon that picks its element."""
    moby = catalog.card(5)  # Moby Morpher, the Morpher — prints ?/?/? until it is played

    boosted = as_boost(moby, "fire")

    assert boosted.stats == {"force": 1, "agility": 1, "intellect": 1}
    assert boosted.element == "fire"


def test_a_dragon_boost_enters_the_queue_as_itself(catalog):
    """Only the Morpher has a boost mode; every other boost rides in unchanged, its own element kept."""
    dragon = catalog.card(1)  # Silver Manta Ray — a dragon, 1/1/1 of water

    boosted = as_boost(dragon, "fire")

    assert boosted.stats == dragon.stats
    assert boosted.element == dragon.element  # the ask is ignored — not a Morpher


def test_a_hand_or_play_wu_is_never_offered_the_boost_slot(catalog):
    rejected = {mechanic_of(power) for power in catalog.powers if not is_boost_slot(power)}

    assert Mechanic.DRAGON not in rejected
    assert Mechanic.BOOST not in rejected
    assert Mechanic.PRINTED_STATS in rejected


# --- the player's word for a trigger, not the DB's ---------------------------------


def test_a_deposit_trigger_never_says_deposit(catalog):
    """To deposit a Wu is to bank it for points, which forfeits the power.

    So "On Deposit" names the one action that guarantees the power never fires. It fires on Use.
    """
    from xiaolin_showdown.screens.format import trigger_label

    labels = {trigger_label(p) for p in catalog.powers if trigger_of(p) == "use"}

    assert "On Deposit" not in labels
    assert labels <= {"On Use", "? ? ?"}


def test_a_hand_trigger_says_it_is_passive(catalog):
    """`hand` powers do not fire on anything — they apply for as long as the Wu is held."""
    from xiaolin_showdown.screens.format import trigger_label

    assert {trigger_label(p) for p in catalog.powers if trigger_of(p) == "hand"} == {"While Held"}


# --- what a Wu tells you it does ---------------------------------------------------


SILENT = {Mechanic.FILLER, Mechanic.PRINTED_STATS, Mechanic.INITIATIVE, Mechanic.GAMBLE}


def test_every_mechanic_either_explains_itself_or_is_deliberately_silent(catalog):
    """A Wu whose rule appears nowhere can only be learned by losing a run to it.

    Four say nothing on purpose: deck filler has no power, a plain Wu's stats are the whole of it,
    an initiative Wu already prints its bonus, and the joke Wu tells you nothing by design.
    """
    from xiaolin_showdown.screens.format import effect_line

    for power in catalog.powers:
        mechanic = mechanic_of(power)
        if mechanic in SILENT:
            assert effect_line(power) is None, f"{mechanic} should say nothing"
        else:
            assert effect_line(power), f"{mechanic} does what, exactly? Nothing says."


def test_a_hidden_power_still_states_its_rule(catalog):
    """A character's dragon keeps its *name* to itself. The rule it plays by is not a secret."""
    from xiaolin_showdown.screens.format import effect_line

    born_holding = [
        c
        for c in catalog.cards
        if mechanic_of(c.power) is Mechanic.DRAGON and c.power.id < 0
    ]

    assert born_holding
    for card in born_holding:
        assert -5 < card.power.id < 0, "no longer hidden — this test is guarding nothing"
        assert effect_line(card.power)


def test_a_wudai_weapon_can_be_found_rather_than_inherited(catalog):
    """Not every dragon is born in a hand. One waits in the pile to be won.

    The negative power id marks the Wu a character was born holding; a wudai weapon printed into the
    draw pile is the same mechanic with none of the birthright — it can be staked, won and lost.
    """
    from xiaolin_showdown.screens.format import effect_line

    found = [
        c
        for c in catalog.cards
        if mechanic_of(c.power) is Mechanic.DRAGON and c.id >= FIRST_DECK_CARD
    ]

    assert found, "the pile holds no wudai weapon"
    for card in found:
        assert card.power.id > 0, "a found dragon is not a birthright"
        assert effect_line(card.power)


def test_a_wudai_reads_as_possession_on_its_owner_and_as_the_weapons_rule_on_the_wu(catalog):
    """Same mechanic, two readings: a character *possesses* the weapon; the Wu *is* it.

    True of a dragon (a born-holding character) and of Hannibal, whose Morpher is his wudai.
    """
    from copy import deepcopy

    from xiaolin_showdown.logic.mechanics.cards import held_as_wudai
    from xiaolin_showdown.screens.format import effect_line, points_label, trigger_label

    omi = catalog.character(1)  # a dragon character
    hannibal = catalog.character(11)  # holds Moby Morpher as his wudai
    found_dragon = next(
        c for c in catalog.cards
        if mechanic_of(c.power) is Mechanic.DRAGON and c.id >= FIRST_DECK_CARD
    )

    # The character possesses a weapon; Hannibal's is his one immutable Morpher.
    assert "Wudai weapon" in (effect_line(omi.power, is_card=False) or "")
    assert effect_line(hannibal.power, is_card=False) == "Immutable Moby Morpher."
    # And a possessed wudai reads "On Boost" on its owner, whatever the Wu's own trigger.
    assert trigger_label(hannibal.power, is_card=False) == "On Boost"
    # On the Wu itself, the weapon states its own rule.
    assert "Boost" in (effect_line(found_dragon.power, is_card=True) or "")

    # The Morpher: fielded from the pool it is On Play and bankable; as a wudai it is On Boost, worth X.
    pool = catalog.card(5)
    wudai = held_as_wudai(deepcopy(pool))
    assert trigger_label(pool.power, is_card=True, card_type=pool.type) == "On Play"
    assert trigger_label(wudai.power, is_card=True, card_type=wudai.type) == "On Boost"
    assert points_label(wudai) == "X"
    assert points_label(pool) == str(pool.points)

    # The Shimo Staff (card 44) is a wudai found in the pile — boost-only, but banked like any Wu.
    shimo = catalog.card(44)
    assert trigger_label(shimo.power, is_card=True, card_type=shimo.type) == "On Boost"
    assert points_label(shimo) == str(shimo.points)  # the exception: it shows its real points
    assert points_label(catalog.card(1)) == "X"  # a born dragon never counts
