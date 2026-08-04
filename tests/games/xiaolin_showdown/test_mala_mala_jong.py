"""Mala Mala Jong — the assembly transform (logic/characters/jong.py).

The construct is a costume over the real duelist: a screen sees 6/6/6 ``Mala Mala Jong``, but every
rule that reads *who* is playing still sees the real character underneath. These pin the pure state —
the gate, the purge, the overlay — that the temple and duel layers build on.
"""

from __future__ import annotations

from copy import deepcopy

from termcade.core.rng import Rng

from factories import auto_choices

from xiaolin_showdown.logic.characters import jong
from xiaolin_showdown.logic.flow import bot
from xiaolin_showdown.logic.flow.actions import can_construct, construct_jong
from xiaolin_showdown.logic.flow.battle import Round
from xiaolin_showdown.logic.schema.catalog import load_catalog
from xiaolin_showdown.logic.flow.duel import Duel
from xiaolin_showdown.logic.flow.outcome import final_score
from xiaolin_showdown.logic.flow.actions import draw_blocked
from xiaolin_showdown.logic.schema.models import Mechanic, Player
from xiaolin_showdown.logic.mechanics.powers import is_jong_bane, mechanic_of
from xiaolin_showdown.logic.config.settings import XiaolinSettings
from xiaolin_showdown.logic.flow.setup import new_game


def _card_of_type(cat, slot):
    return deepcopy(next(c for c in cat.cards if c.type == slot))


def _heart(cat):
    return deepcopy(next(c for c in cat.cards if mechanic_of(c.power) is Mechanic.ANIMATE))


def _full_builder() -> Player:
    """A duelist holding one Wu of each of the five slots plus the Heart — a set ready to assemble."""
    cat = load_catalog()
    hand = [_card_of_type(cat, slot) for slot in jong.PART_TYPES] + [_heart(cat)]
    return Player(character=deepcopy(cat.character(1)), hand=hand)  # Omi


def test_can_construct_needs_every_slot_and_the_heart():
    assert jong.can_construct(_full_builder())


def test_a_missing_heart_closes_the_gate():
    builder = _full_builder()
    builder.hand = [c for c in builder.hand if mechanic_of(c.power) is not Mechanic.ANIMATE]
    assert not jong.can_construct(builder)


def test_a_missing_part_closes_the_gate():
    builder = _full_builder()
    builder.hand = [c for c in builder.hand if c.type != "torso"]  # the rarest slot, the real gate
    assert not jong.can_construct(builder)


def test_construct_stands_up_a_six_six_six_body():
    builder = _full_builder()
    jong.construct(builder)
    assert bot.is_jong(builder)
    assert set(jong.battle_stats(builder).values()) == {jong.JONG_STAT}


def test_construct_keeps_the_body_and_exiles_the_heart():
    builder = _full_builder()
    jong.construct(builder)
    assert sorted(c.type for c in builder.hand) == sorted(jong.PART_TYPES)  # the five parts, nothing else
    assert not any(mechanic_of(c.power) is Mechanic.ANIMATE for c in builder.hand)  # Heart is gone
    assert mechanic_of(builder.jong_heart.power) is Mechanic.ANIMATE  # ...held out of play


def test_construct_deposits_every_other_wu_for_points():
    builder = _full_builder()
    cat = load_catalog()
    junk = deepcopy(next(c for c in cat.cards if c.type == "item" and mechanic_of(c.power) is not Mechanic.ANIMATE))
    builder.hand.append(junk)
    before = builder.points
    purged = jong.construct(builder)
    assert junk in purged
    assert junk in builder.vault
    assert builder.points == before + junk.points


def test_construct_keeps_a_wudai_weapon():
    builder = _full_builder()
    cat = load_catalog()
    wudai = deepcopy(next(c for c in cat.cards if c.type == "wudai"))
    builder.hand.append(wudai)
    jong.construct(builder)
    assert wudai in builder.hand


def test_the_costume_is_an_overlay_the_real_character_shows_through():
    builder = _full_builder()
    jong.construct(builder)
    assert jong.shown_name(builder) == jong.JONG_NAME
    assert jong.shown_affiliation(builder) == jong.JONG_AFFILIATION
    assert builder.character.name == "Omi"  # the real duelist is untouched underneath
    assert builder.character.affiliation == "xiaolin"


def test_out_of_form_the_stats_and_name_are_the_real_ones():
    builder = _full_builder()  # not constructed
    assert jong.battle_stats(builder) is builder.character.stats
    assert jong.shown_name(builder) == "Omi"


def test_revert_drops_the_form_and_releases_the_heart():
    builder = _full_builder()
    jong.construct(builder)
    heart = jong.revert(builder)
    assert not bot.is_jong(builder)
    assert builder.jong_heart is None
    assert mechanic_of(heart.power) is Mechanic.ANIMATE  # handed back to the caller to place


# --- the temple verb (actions.construct_jong) ---------------------------------------------------

def _state_with_full_set():
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))  # player is Omi
    state.player.hand = _full_builder().hand
    state.actions_taken = 0
    return state


def test_the_temple_offers_construct_with_a_full_set_and_an_action():
    assert can_construct(_state_with_full_set(), 1)


def test_a_spent_turn_cannot_also_construct():
    state = _state_with_full_set()
    state.actions_taken = 1  # the one action is gone
    assert not can_construct(state, 1)


def test_constructing_spends_the_turns_action():
    state = _state_with_full_set()
    construct_jong(state, is_player=True)
    assert bot.is_jong(state.player)
    assert state.actions_taken == 1  # the transform cost the turn's action


# --- the locked state ----------------------------------------------------------------------------

def test_a_won_wu_is_banked_not_taken_into_the_locked_hand():
    builder = _full_builder()
    jong.construct(builder)
    hand_before = list(builder.hand)
    prize = _card_of_type(load_catalog(), "item")
    jong.deposit_won(builder, prize)
    assert builder.points == prize.points
    assert prize in builder.vault  # vaulted, so a Treasurebox can still wish it back
    assert builder.hand == hand_before  # the locked hand only ever shrinks


def test_the_form_locks_drawing():
    state = _state_with_full_set()
    cat = load_catalog()
    state.player.deck = [_card_of_type(cat, "item")]  # a Wu waiting to be drawn, action unspent
    assert draw_blocked(state, XiaolinSettings()) is None  # ordinary Omi may draw it
    construct_jong(state, is_player=True)
    state.actions_taken = 0  # isolate the lock: a fresh action, so the block can only be the form
    assert draw_blocked(state, XiaolinSettings()) is not None  # the construct may not


# --- winning and losing in the form --------------------------------------------------------------

def _duel_with_jong_player():
    """A duel whose player has assembled the construct — ready to force its End."""
    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))
    state.player.hand = _full_builder().hand
    construct_jong(state, is_player=True)
    return Duel(state, Rng(1), auto_choices(), XiaolinSettings())  # the drop path consults no choice


def test_reaching_the_end_in_form_wins_outright_against_the_points():
    state = _duel_with_jong_player().state
    state.bot.points = 999  # the construct is far behind on points...
    outcome = final_score(state, Rng(1))
    assert outcome.winner is state.player.character  # ...and wins anyway, for ending in the form


async def test_losing_a_showdown_drops_the_form_and_hands_over_the_heart():
    duel = _duel_with_jong_player()
    state = duel.state
    heart = state.player.jong_heart
    part = state.player.hand[0]  # one part, wagered and about to be lost
    duel.duel.rounds.append(Round(stat="force"))
    duel.duel.winner = False  # the bot took the showdown
    duel.duel.player.stakes = [part]
    state.card_deck = [_card_of_type(load_catalog(), "item")]  # pile not dry — the run goes on

    await duel._end()

    assert not bot.is_jong(state.player)  # the form dropped
    assert heart in state.bot.hand  # the Heart came out of exile to the winner
    assert part in state.bot.hand  # ...along with the wagered part
    assert state.player.jong_heart is None


# --- the form survives a save --------------------------------------------------------------------

def test_a_save_taken_in_the_form_restores_the_form_and_the_exiled_heart():
    from xiaolin_showdown.logic.schema.state import XiaolinState

    state = _state_with_full_set()
    construct_jong(state, is_player=True)
    heart_id = state.player.jong_heart.id

    restored = XiaolinState.restore(state.snapshot(), None)

    assert bot.is_jong(restored.player)  # the form came back
    assert restored.player.jong_heart is not None and restored.player.jong_heart.id == heart_id


def test_an_old_save_loads_as_an_ordinary_duelist():
    from xiaolin_showdown.logic.schema.state import XiaolinState

    state = _state_with_full_set()
    snapshot = state.snapshot()
    del snapshot["player"]["jong_form"]  # a save from before the form ever existed
    del snapshot["player"]["jong_heart"]

    restored = XiaolinState.restore(snapshot, None)
    assert not bot.is_jong(restored.player)
    assert restored.player.jong_heart is None


# --- the showdown as Jong: the Heart boost, and the Emperor Scorpion bane ------------------------

def test_the_form_boosts_only_with_its_exiled_heart():
    duel = _duel_with_jong_player()
    duel.duel.rounds.append(Round(stat="force"))
    options = duel._boost_options(duel.state.player, is_player=True)
    assert len(options) == 1 and options[0] is duel.state.player.jong_heart


def test_the_heart_boost_is_a_flat_metal_body_with_no_counter():
    duel = _duel_with_jong_player()
    duel.duel.rounds.append(Round(stat="force"))
    heart = duel.state.player.jong_heart
    duel._commit_boost(heart, is_player=True, element="water")  # a water arena — but Jong's is metal
    boosted = duel.duel.round.player.queue[-1]
    assert set(boosted.stats.values()) == {jong.JONG_BOOST_STAT}  # a flat 1/1/1
    assert boosted.element == "metal"  # as itself, never the arena
    assert duel.duel.round.heart_summoner is None  # no summon → the opponent gets no off-wager answer
    assert heart not in duel.duel.player.stakes  # exiled: a boost can never lose it


def test_emperor_scorpion_is_the_bane_the_heart_is_not():
    cat = load_catalog()
    assert is_jong_bane(cat.card(34).power)  # Emperor Scorpion
    assert not is_jong_bane(cat.card(74).power)  # the Heart of Jong is not


def test_the_bane_wins_the_battle_whatever_the_score():
    duel = _duel_with_jong_player()
    duel.duel.rounds.append(Round(stat="force"))
    duel.duel.round.bane_winner = False  # the Scorpion handed the bot this battle
    duel._score_round(duel.duel.round)
    assert duel.duel.round.winner is False  # the ground did not decide it


# --- the form's own fear and desire --------------------------------------------------------------

def test_the_construct_fears_the_vault():
    from xiaolin_showdown.logic.flow.summons import summon_name

    omi = load_catalog().character(1)
    got = summon_name("{fear}", caster=omi, target=omi, arena="metal", target_is_jong=True)
    assert got == "the Shen Gong Wu Vault"  # not Omi's squirrel — the construct's own dread


def test_the_construct_desire_reads_the_real_side_beneath():
    from xiaolin_showdown.logic.flow.summons import summon_name

    cat = load_catalog()
    xiaolin, heylin = cat.character(1), cat.character(5)  # Omi, Tubbimura
    assert summon_name("{desire}", caster=xiaolin, target=xiaolin, arena="metal", caster_is_jong=True) == "World Peace"
    assert summon_name("{desire}", caster=heylin, target=heylin, arena="metal", caster_is_jong=True) == "World Domination"


def test_out_of_form_the_fear_pool_is_unchanged():
    from xiaolin_showdown.logic.flow.summons import summon_name

    omi = load_catalog().character(1)
    assert summon_name("{fear}", caster=omi, target=omi, arena="metal") == "a Squirrel"


# --- the set breaking any other way (steal / bounce / transfer / wear-out) -----------------------

def test_a_broken_set_drops_the_form_and_brings_the_heart_home():
    builder = _full_builder()
    jong.construct(builder)
    builder.hand.pop()  # a part stolen / bounced / worn away
    heart = jong.drop_if_broken(builder)
    assert not bot.is_jong(builder)
    assert heart is not None and heart in builder.hand  # home to this duelist, not to an opponent
    assert builder.jong_heart is None


def test_an_intact_set_keeps_the_form():
    builder = _full_builder()
    jong.construct(builder)
    assert jong.drop_if_broken(builder) is None  # nothing left the hand
    assert bot.is_jong(builder)


# --- the bot policy ------------------------------------------------------------------------------

def test_the_bot_assembles_the_moment_it_holds_the_set():
    from termcade.core.settings import Difficulty

    from xiaolin_showdown.logic.flow.turn import bot_turn

    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))
    state.bot.hand = _full_builder().hand
    state.bot_actions_taken = 0
    bot_turn(state, XiaolinSettings(), rng=Rng(1), difficulty=Difficulty.HARD)
    assert bot.is_jong(state.bot)  # construct outranks every other temple move


def test_a_jong_bot_takes_no_temple_action_so_witchcraft_cannot_break_the_lock():
    from termcade.core.settings import Difficulty

    from xiaolin_showdown.logic.flow.turn import bot_turn

    cat = load_catalog()
    state = new_game(cat, Rng(1), cat.character(1))
    state.bot.character = deepcopy(cat.character(12))  # Wuya — her witchcraft recalls the oldest lost Wu
    state.bot.hand = _full_builder().hand
    jong.construct(state.bot)
    state.lost = [_card_of_type(cat, "item")]  # a Wu her recall would pull into the locked hand, if she acted
    state.bot_actions_taken = 0
    before = list(state.bot.hand)
    bot_turn(state, XiaolinSettings(), rng=Rng(1), difficulty=Difficulty.BOSS)
    assert bot.is_jong(state.bot)  # still whole
    assert state.bot.hand == before  # no Wu recalled in, no part banked out — the lock held


def test_jong_never_flies_the_early_bird():
    """It is out for the fight, and its only Wu are parts — flying would break the set."""
    from xiaolin_showdown.logic.flow.actions import can_early_bird

    state = _state_with_full_set()
    construct_jong(state, is_player=True)
    state.actions_taken = 0  # a fresh action, so only the form can be the blocker
    assert not can_early_bird(state, XiaolinSettings())


def test_the_bot_never_boosts_the_normal_heart():
    """Boosting the Heart hands the opponent a free off-wager Wu — the bot fields it instead of gifting."""
    from xiaolin_showdown.logic.flow import bot
    from xiaolin_showdown.logic.flow.battle import Ground, Round

    cat = load_catalog()
    ground = Ground(stats=("force", "agility", "intellect"), background="metal", player_stats={}, bot_stats={})
    heart = _heart(cat)
    plain = _card_of_type(cat, "item")
    assert bot.choose_boost(Round(stat="force"), ground, [heart], [plain]) is None
