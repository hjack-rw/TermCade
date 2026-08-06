"""Summon Wu (TRAIN_BOOST): spent at the temple they shove +TRAIN_BOOST_STEP into the training bar and
are discarded. Fielded, they show what they call up — the beast follows the arena element.
"""

from __future__ import annotations

from copy import deepcopy

from termcade.core.rng import Rng

from dataclasses import replace

from factories import auto_choices, plain_wu, run_showdown, summon_wu

from xiaolin_showdown.logic.flow.actions import usable_powers, use_power
from xiaolin_showdown.logic.flow.battle import Round
from xiaolin_showdown.logic.schema.catalog import load_catalog
from xiaolin_showdown.logic.flow.duel import Duel
from xiaolin_showdown.logic.mechanics.powers import Mechanic, mechanic_of
from xiaolin_showdown.logic.config.settings import XiaolinSettings
from xiaolin_showdown.logic.flow.setup import new_game
from xiaolin_showdown.logic.flow.training import train_boost_step

DEFAULT = XiaolinSettings()
STAT_CAP = DEFAULT.stat_cap
TRAIN_BOOST_STEP = train_boost_step(0, DEFAULT)  # the base (weakest) tier's step, at the shipped bar length

# TRAIN_BOOST has six Wu; each is genuinely specific here — the summon template is what each test is
# actually about (a plain "{beast}" vs a fixed non-template curse vs a higher tier), so pick by that.
_CAT = load_catalog()
PLAIN_WU = plain_wu(_CAT).id
TONGUE = summon_wu(_CAT, "{beast}").id
IMO = summon_wu(_CAT, "{drawing}").id
ZING = summon_wu(_CAT, "a Horde of Zombies").id
MONARCH = summon_wu(_CAT, "{spirit}").id
MOONSTONE = summon_wu(_CAT, "{desire}").id
SAPPHIRE = summon_wu(_CAT, "the Sapphire Dragon").id
SHADOW_OF_FEAR = summon_wu(_CAT, "{fear}").id


def _seed(state, cid):
    card = deepcopy(state.catalog.card(cid))
    state.player.hand.append(card)
    return card


# --- the temple side: spend it to train ------------------------------------------


def test_spending_a_summon_shoves_the_training_bar(state):
    tongue = _seed(state, TONGUE)
    before = state.player.training
    use_power(state, tongue, DEFAULT, is_player=True, rng=Rng(1))
    assert state.player.training == before + TRAIN_BOOST_STEP


def test_a_spent_summon_leaves_the_hand(state):
    # The dealt hand can hold a stray TRAIN_BOOST Wu of its own — strip it, so only the seeded one
    # is in play and its removal is what the assertion below is actually checking.
    state.player.hand = [c for c in state.player.hand if mechanic_of(c.power) is not Mechanic.TRAIN_BOOST]
    tongue = _seed(state, TONGUE)
    use_power(state, tongue, DEFAULT, is_player=True, rng=Rng(1))
    assert not any(mechanic_of(c.power) is Mechanic.TRAIN_BOOST for c in state.player.whole_hand)


def test_a_higher_tier_summon_shoves_its_own_step(state):
    """The +6 Wu carry their own ``train_step``; the bar reads it off the card, not the base constant."""
    monarch = _seed(state, MONARCH)
    assert monarch.power.train_step > TRAIN_BOOST_STEP  # a higher tier, and it says so on the card
    before = state.player.training
    use_power(state, monarch, DEFAULT, is_player=True, rng=Rng(1))
    assert state.player.training == before + monarch.power.train_step


def test_the_sapphire_dragon_fills_the_whole_bar_from_empty(state):
    """Its boost is as big as the bar, so from any progress it tops out — one level, on the spot. Read
    off the card: the moment the bar length outgrows its step, this fails and points here."""
    from xiaolin_showdown.logic.flow.training import payout_ready

    sapphire = _seed(state, SAPPHIRE)
    assert sapphire.power.train_step >= DEFAULT.train_length_player  # a full-bar boost, the card says so
    state.player.training = 0
    use_power(state, sapphire, DEFAULT, is_player=True, rng=Rng(1))
    assert payout_ready(state.player, DEFAULT)  # a level waits, from an empty bar


def test_the_sapphire_dragon_rests_metal_but_scores_nothing(state):
    """It rests metal, but its ?/?/? stats give the arena bonus nothing to land on — and fielding it
    loses the showdown outright anyway (is_uncontrolled), so the element is cosmetic."""
    sapphire = state.catalog.card(SAPPHIRE)
    assert sapphire.element == "metal"
    assert all(value is None for value in sapphire.stats.values())


def test_a_summon_is_hidden_once_every_stat_is_capped(state):
    _seed(state, TONGUE)
    for stat in state.player.character.stats:
        state.player.character.stats[stat] = STAT_CAP
    offered = [c for c in usable_powers(state, 1, DEFAULT) if mechanic_of(c.power) is Mechanic.TRAIN_BOOST]
    assert not offered


# --- the board side: the summon follows the arena --------------------------------


def _duel_on(background):
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))  # Omi
    duel = Duel(state, Rng(1), auto_choices())
    duel.duel.background = background
    return duel


def test_the_animal_follows_the_arena_element():
    duel = _duel_on("water")
    assert duel._summon_display(deepcopy(duel.state.catalog.card(TONGUE)), is_player=True) == "a Pod of Seals"


def test_a_metal_arena_summons_a_troop_of_monkeys():
    duel = _duel_on("metal")
    assert duel._summon_display(deepcopy(duel.state.catalog.card(TONGUE)), is_player=True) == "a Troop of Monkeys"


def test_the_drawing_is_a_mythic_beast_of_the_arena():
    """Imo Gazer draws its own pool to life — the Four Symbols and the Qilin, one per element."""
    duel = _duel_on("wind")
    got = duel._summon_display(deepcopy(duel.state.catalog.card(IMO)), is_player=True)
    assert got == "the Azure Dragon"


def test_the_zombies_are_fixed_whatever_the_arena():
    duel = _duel_on("fire")
    assert duel._summon_display(deepcopy(duel.state.catalog.card(ZING)), is_player=True) == "a Horde of Zombies"


# --- the caster-keyed summons: chosen by who fields it, not the arena -------------


def _duel_as(char_id):
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(char_id))
    duel = Duel(state, Rng(1), auto_choices())
    duel.duel.background = "metal"  # set, to prove it plays no part in these
    return duel


def _monarch(duel):
    return duel._summon_display(deepcopy(duel.state.catalog.card(MONARCH)), is_player=True)


def test_the_xiaolin_spirit_is_a_chi_creature():
    assert _monarch(_duel_as(1)) == "Chi Creature"  # Omi


def test_a_heylin_spirit_is_sibini():
    assert _monarch(_duel_as(13)) == "Sibini"  # Chase Young


def test_hannibal_alone_draws_the_ying_yang_bird():
    """A Yin-Yang world native; no Sibini answers him."""
    assert _monarch(_duel_as(11)) == "Ying-Yang Bird"  # Hannibal


def test_the_desire_is_the_casters_own():
    duel = _duel_as(1)  # Omi
    got = duel._summon_display(deepcopy(duel.state.catalog.card(MOONSTONE)), is_player=True)
    assert got == "his Long Lost Parents"


def _bot_temple_state(cards, bar):
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))
    state.bot.character = cat.character(6)  # Katnappé — room under the cap to train
    state.bot.hand = [deepcopy(cat.card(c)) for c in cards]
    state.bot.training = bar
    return state


def test_the_bot_spends_the_sapphire_dragon_to_train():
    """It can never field it, so the temple is the only use — and its full-bar boost is a free level."""
    from xiaolin_showdown.logic.flow.temple_ai import choose_temple_power

    play = choose_temple_power(_bot_temple_state([SAPPHIRE, PLAIN_WU], 0), XiaolinSettings(), is_player=False)
    assert play is not None and play.card.id == SAPPHIRE


def test_the_bot_feeds_a_summon_only_when_it_completes_a_level():
    """A +3 is worth more fielded than fed to a low bar; near the top, it finishes a level and pays out."""
    from xiaolin_showdown.logic.flow.temple_ai import choose_temple_power

    settings = XiaolinSettings()
    low = choose_temple_power(_bot_temple_state([TONGUE, PLAIN_WU], 2), settings, is_player=False)
    high = choose_temple_power(_bot_temple_state([TONGUE, PLAIN_WU], 8), settings, is_player=False)
    assert low is None  # 2 + 3 falls short of a full bar
    assert high is not None and high.card.id == TONGUE  # 8 + 3 completes it


def _duel_where_the_player_fields_the_dragon():
    cat = load_catalog()
    rng = Rng(1)
    state = new_game(cat, rng, cat.character(1))
    state.player.hand = [deepcopy(cat.card(SAPPHIRE)), deepcopy(cat.card(PLAIN_WU))]
    state.forced_priority = True  # the player leads and names the challenge

    async def _play_dragon(playable):
        return next((c for c in playable if c.id == SAPPHIRE), playable[0])

    choices = replace(auto_choices(), card=_play_dragon)
    return state, Duel(state, rng, choices)


async def test_fielding_the_sapphire_dragon_loses_the_showdown():
    _state, duel = _duel_where_the_player_fields_the_dragon()
    await run_showdown(duel, XiaolinSettings())
    assert duel.duel.auto_winner is False  # the dragon turned on its summoner — not a stat loss
    assert duel.duel.winner is False  # ...and that decides it, whatever the board said


def test_the_bot_holds_the_sapphire_dragon_back():
    """The bot never throws a showdown on it: given anything else that can fight, it fields that."""
    from factories import ground

    from xiaolin_showdown.logic.flow.bot import choose_card

    cat = load_catalog()
    dragon = deepcopy(cat.card(SAPPHIRE))
    fist = deepcopy(cat.card(PLAIN_WU))
    chosen = choose_card(Round(stat="force"), ground(), [fist, dragon], Rng(1))
    assert chosen.id != SAPPHIRE


def _duel_targeting(bot_char_id: int) -> Duel:
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))  # the player is Omi
    state.bot.character = cat.character(bot_char_id)
    duel = Duel(state, Rng(1), auto_choices())
    duel.duel.rounds.append(Round(stat="force"))
    return duel


def test_the_fear_is_the_targets_not_the_casters():
    """Shadow of Fear gives a body to the worst fear of whoever it lands on — the caster's opponent."""
    from xiaolin_showdown.logic.flow.summons import _FEARS

    duel = _duel_targeting(13)  # the bot is Chase Young
    fear = deepcopy(load_catalog().card(SHADOW_OF_FEAR))
    assert duel._summon_display(fear, is_player=True) == _FEARS["Chase_Young"]  # player casts on Chase
    assert duel._summon_display(fear, is_player=False) == _FEARS["Omi"]  # bot casts on Omi


def test_a_target_with_no_fear_named_meets_a_nameless_dread():
    from xiaolin_showdown.logic.flow.summons import _A_NAMELESS_DREAD

    duel = _duel_targeting(1)
    nameless = deepcopy(duel.state.bot.character)
    nameless.name = "Nobody"  # not in _FEARS
    duel.state.bot.character = nameless
    assert duel._summon_display(deepcopy(load_catalog().card(SHADOW_OF_FEAR)), is_player=True) == _A_NAMELESS_DREAD


def test_every_duelist_has_a_desire():
    """Moonstone conjures per character, so a fighter added to the roster needs its own entry — without
    one it silently falls back to a plain figment. This is the guard the fallback would otherwise hide."""
    from xiaolin_showdown.logic.flow.summons import _DESIRES

    duelists = [c for c in load_catalog().characters if c.affiliation in {"xiaolin", "heylin"}]
    missing = [c.name for c in duelists if c.name not in _DESIRES]
    assert not missing, f"characters with no Moonstone desire: {missing}"
