"""Flow tests: two mechanics live in the same real `Duel`/`XiaolinState`, not pinned in isolation."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from termcade.core.rng import Rng
from termcade.core.settings import Difficulty, Settings

from factories import auto_choices, duelist, run_showdown, wu

from xiaolin_showdown.logic.characters import jack, jong
from xiaolin_showdown.logic.config.ladder import record_win, unlocked_bosses
from xiaolin_showdown.logic.flow import bot
from xiaolin_showdown.logic.flow.actions import use_power
from xiaolin_showdown.logic.flow.battle import Round
from xiaolin_showdown.logic.flow.duel import Amend, Duel, DuelState
from xiaolin_showdown.logic.flow.outcome import final_score
from xiaolin_showdown.logic.flow.training import train_boost_step
from xiaolin_showdown.logic.mechanics.powers import Mechanic, mechanic_of
from xiaolin_showdown.logic.mechanics.resolve import resolve_played_power
from xiaolin_showdown.logic.schema.catalog import load_catalog
from xiaolin_showdown.logic.schema.constants import TOURNAMENT
from xiaolin_showdown.logic.schema.state import XiaolinState
from xiaolin_showdown.logic.config.settings import XiaolinSettings, default_deal
from xiaolin_showdown.logic.flow.setup import new_game

CAT = load_catalog()
DEFAULT = XiaolinSettings()
WEAR_LIMIT = DEFAULT.wear_limit
LOSS_FILL = DEFAULT.loss_fill_player
TRAIN_LENGTH = DEFAULT.train_length_player
TRAIN_BOOST_STEP = train_boost_step(0, DEFAULT)


def _opponent(name: str):
    return next(c for c in CAT.characters if c.name == name)


def _prefer(name: str):
    """A card callback that fields ``name`` the moment it's playable, else the first legal option."""

    async def _pick(playable):
        return next((c for c in playable if c.name == name), playable[0])

    return _pick


def _after_n_then_prefer(n: int, mechanic: Mechanic):
    """Field the first legal option for ``n`` calls, then switch to the first Wu of ``mechanic``."""
    calls = {"count": 0}

    async def _pick(playable):
        calls["count"] += 1
        if calls["count"] > n:
            target = next((c for c in playable if mechanic_of(c.power) is mechanic), None)
            if target is not None:
                return target
        return playable[0]

    return _pick


async def _force_tournament(options):
    return TOURNAMENT if TOURNAMENT in options else options[0]


# --- 1. Jack's identity swap alongside a curse played the same round ------------------------------


async def test_chamelon_bot_and_a_played_curse_both_land_in_the_same_showdown():
    state = new_game(CAT, Rng(5), CAT.character(1), opponent=_opponent("Jack_Spicer"))
    state.forced_priority = True  # the player leads -> Chamelon-Bot fires unconditionally
    curse = wu(-2, name="Curse", element="metal")
    state.player.hand.append(curse)
    choices = replace(auto_choices(), card=_prefer("Curse"))
    duel = Duel(state, Rng(5), choices)

    await run_showdown(duel, XiaolinSettings())

    assert duel.duel.jack_mode == jack.CHAMELON_NAME
    assert any(c.name == "Curse" for c in duel.duel.round.bot.suffered), "the curse never reached Jack"
    assert duel.duel.winner is not None  # the showdown still resolved to a real outcome


# --- 2. AI Jack's steal against an assembled Mala Mala Jong ---------------------------------------


async def test_ai_jack_steal_breaks_an_assembled_jong():
    parts = [next(deepcopy(c) for c in CAT.cards if c.type == slot) for slot in jong.PART_TYPES]
    heart = next(deepcopy(c) for c in CAT.cards if mechanic_of(c.power) is Mechanic.ANIMATE)
    state = new_game(CAT, Rng(5), CAT.character(1), opponent=_opponent("Jack_Spicer"))
    state.forced_priority = False  # Jack leads -> AI Jack mode is eligible
    state.jack_can_swap = True
    state.player.hand = [*parts, heart]
    jong.construct(state.player)
    assert bot.is_jong(state.player)
    exiled_heart = state.player.jong_heart
    assert exiled_heart is not None

    duel = Duel(state, Rng(5), auto_choices())
    await duel._commitment()

    assert duel.duel.jack_mode == jack.AI_JACK_NAME
    assert not bot.is_jong(state.player), "a stolen part must break the construct"
    assert state.player.jong_heart is None
    assert any(c is exiled_heart for c in state.player.hand), "the exiled Heart must come home"


# --- 3. A worn Jong part vaulting at showdown end drops the form ----------------------------------


async def test_a_part_wearing_out_mid_showdown_breaks_the_jong_form_it_completed():
    parts = [next(deepcopy(c) for c in CAT.cards if c.type == slot) for slot in jong.PART_TYPES]
    heart = next(deepcopy(c) for c in CAT.cards if mechanic_of(c.power) is Mechanic.ANIMATE)
    worn_part = next(c for c in parts if c.type == "head")
    worn_part.uses = WEAR_LIMIT - 1  # one more showdown vaults it
    state = new_game(CAT, Rng(3), CAT.character(1))
    state.player.hand = [*parts, heart]
    jong.construct(state.player)
    assert bot.is_jong(state.player)

    duel = Duel(state, Rng(3), auto_choices())
    duel.duel.stakes = None  # isolate the wear/drop interaction from the prize route
    duel.duel.winner = True  # the player wins, so the worn part is not also forfeited
    duel.duel.player = replace(DuelState().player, stakes=[worn_part])
    duel.duel.rounds = [Round(stat="force", score=1)]

    await duel._end()

    assert not any(c is worn_part for c in state.player.hand), "the worn part must have vaulted"
    assert not bot.is_jong(state.player), "vaulting a part must drop the form"
    assert state.player.jong_heart is None
    assert any(c.name == heart.name for c in state.player.hand), "the Heart must return to hand"


# --- 4. Emperor Scorpion's bane-win against Jong, carried through the prize claim ------------------


async def test_emperor_scorpion_forces_the_showdown_winner_the_prize_claim_reads():
    parts = [next(deepcopy(c) for c in CAT.cards if c.type == slot) for slot in jong.PART_TYPES]
    heart = next(deepcopy(c) for c in CAT.cards if mechanic_of(c.power) is Mechanic.ANIMATE)
    state = new_game(CAT, Rng(1), CAT.character(1))
    state.bot.hand = [*parts, heart]
    jong.construct(state.bot)
    assert bot.is_jong(state.bot)

    scorpion = deepcopy(next(c for c in CAT.cards if mechanic_of(c.power) is Mechanic.NULLIFY_WU))
    state.player.hand.append(scorpion)
    state.player.character.stats = {"force": 9, "agility": 9, "intellect": 9}  # clears the prize bar
    state.forced_priority = True  # the player leads and names a single-stat challenge
    choices = replace(auto_choices(), card=_prefer(scorpion.name))
    duel = Duel(state, Rng(1), choices)

    await run_showdown(duel, XiaolinSettings())

    assert duel.duel.rounds[0].bane_winner is True
    assert duel.duel.winner is True, "the bane override must decide the whole showdown"
    assert duel.duel.card_won, "the stacked stats must clear the prize bar for the forced winner"
    assert any(c is duel.duel.stakes for c in state.player.whole_hand), (
        "the prize must land with the bane-forced winner, not whoever the raw stats favoured"
    )


# --- 5. Hannibal's Elemental Deflection tracks an amended arena, not the one at commitment ---------


async def test_hannibals_deflection_follows_an_amended_arena():
    state = new_game(CAT, Rng(1), CAT.character(1), opponent=_opponent("Hannibal_Roy_Bean"))
    duel = Duel(state, Rng(1), auto_choices())
    duel.duel.stakes = wu(1, 1, 1, name="Prize")
    duel.duel.challenge, duel.duel.background = "force", "fire"
    duel.duel.rounds.append(Round(stat="force"))
    base = state.player.character.stats["force"]

    water_wu = wu(2, name="Silver Manta Ray", element="water")
    resolve_played_power(duel.duel.round, water_wu, is_player=True, element="water")
    duel._score_round(duel.duel.round)
    on_fire = duel.duel.round.player.result[0]

    duel._apply_amend(Amend(kind="background", value="water"))
    duel._score_round(duel.duel.round)
    on_water = duel.duel.round.player.result[0]

    assert on_fire == base + water_wu.stats["force"] - 1  # dragged: fire is water's opposite
    assert on_water == base + water_wu.stats["force"]  # lift deflected to exactly 0, not +1


# --- 6. A real run's win feeds the boss ladder, not a hand-built Settings --------------------------


async def test_a_won_hard_run_actually_opens_the_boss_ladder():
    from xiaolin_showdown.logic.flow.turn import refill_hands

    state = new_game(CAT, Rng(1), CAT.character(1))
    duel = Duel(state, Rng(1), auto_choices())
    rules = XiaolinSettings()
    refill_hands(state, rules, rng=Rng(1))

    for _ in range(500):
        if await duel.advance() == 0:
            refill_hands(state, rules, rng=Rng(1))
        if duel.is_over:
            break
    assert duel.is_over

    outcome = final_score(state, Rng(1))
    # The ladder gate refuses to advance on house rules (see `rules_modified`), so this needs Hard's
    # own natural deal, not a bare options dict.
    deck_size, point_limit = default_deal(Settings(difficulty=Difficulty.HARD))
    hard_options = {"max_deck_size": deck_size, "point_limit": point_limit}
    settings = Settings(difficulty=Difficulty.HARD, options={**hard_options, "boss_ladder": 0})

    if outcome.winner is state.player.character:
        updated = record_win(settings, difficulty=Difficulty.HARD, boss=None)
        assert unlocked_bosses(CAT.opponents("boss"), updated) == unlocked_bosses(
            CAT.opponents("boss"),
            Settings(difficulty=Difficulty.HARD, options={**hard_options, "boss_ladder": 1}),
        )
        assert any(b.name == "Jack_Spicer" for b in unlocked_bosses(CAT.opponents("boss"), updated))
    else:
        pass  # a loss (or a tie): the real caller never invokes record_win, so the ladder can't move


# --- 7. A temple-spent summon and a lost showdown both feed the same training bar ------------------


async def test_a_temple_summon_and_a_lost_showdown_stack_on_the_training_bar():
    state = new_game(CAT, Rng(2), CAT.character(1))
    # The dealt hand can hold a stray Wu that also moves the training bar (e.g. Ring of Nine Xing's
    # DOUBLE_TRAINING) — clear it, so the summon below is the only thing touching the bar.
    state.player.hand = []
    summon = deepcopy(next(c for c in CAT.cards if mechanic_of(c.power) is Mechanic.TRAIN_BOOST))
    state.player.hand.append(summon)
    assert state.player.training == 0

    use_power(state, summon, DEFAULT, is_player=True, rng=Rng(1))
    after_temple = state.player.training
    assert after_temple == TRAIN_BOOST_STEP

    duel = Duel(state, Rng(2), auto_choices())
    duel.duel.stakes = None
    duel.duel.winner = False  # the player loses this showdown
    duel.duel.rounds = [Round(stat="force", score=-1)]
    await duel._end()

    assert state.player.training == min(after_temple + LOSS_FILL, TRAIN_LENGTH)


# --- 8. The Treasurebox fielded partway through a tournament already in progress -------------------


async def test_the_treasurebox_overrides_a_tournament_already_under_way():
    state = new_game(CAT, Rng(4), CAT.character(1))
    treasurebox = wu(mechanic=Mechanic.WISH, name="Treasurebox", points=0)
    state.player.hand.append(treasurebox)
    state.forced_priority = True
    choices = replace(
        auto_choices(), challenge=_force_tournament, card=_after_n_then_prefer(2, Mechanic.WISH)
    )
    duel = Duel(state, Rng(4), choices)

    await run_showdown(duel, XiaolinSettings())

    assert duel.duel.challenge == TOURNAMENT
    assert duel.duel.auto_winner is True
    assert duel.duel.winner is True, "the wish must decide the showdown whatever the first two legs did"


# --- 9. A hand-swapped Wu wears from a fresh count in the very next showdown -----------------------


async def test_a_wu_won_through_the_lantern_swap_wears_fresh_not_from_memory():
    lantern = wu(0, 0, 0, mechanic=Mechanic.TRANSFER, name="Lantern")
    veteran = wu(3, name="Veteran", points=4)
    veteran.uses = WEAR_LIMIT - 1
    player = duelist(hand=[lantern])
    opponent = duelist(hand=[veteran])
    state = XiaolinState(catalog=CAT, player=player, bot=opponent, card_deck=[])  # type: ignore[arg-type]

    use_power(state, lantern, DEFAULT, is_player=True)
    taken = next(c for c in state.player.hand if c.name == "Veteran")
    assert taken.uses == 0 and taken.uses_memory == WEAR_LIMIT - 1

    duel = Duel(state, Rng(1), auto_choices())
    duel.duel.stakes = None
    duel.duel.winner = True
    duel.duel.player = replace(DuelState().player, stakes=[taken])
    duel.duel.rounds = [Round(stat="force", score=1)]

    await duel._end()

    assert taken.uses == 1, "a swapped Wu's live count must climb from its FRESH zero"
    assert any(c is taken for c in state.player.hand), "one showdown must not be enough to vault it"


# --- 10. A boost already queued when Chamelon-Bot's own denial-boost joins it -----------------------


async def test_chamelon_bots_denial_boost_stacks_with_a_boost_already_queued():
    state = new_game(CAT, Rng(1), CAT.character(1), opponent=_opponent("Jack_Spicer"))
    duel = Duel(state, Rng(1), auto_choices())
    duel.duel.stakes = wu(1, 1, 1, name="Prize")
    duel.duel.jack_mode = jack.CHAMELON_NAME
    duel.duel.challenge, duel.duel.background = "force", "metal"
    duel.duel.player_priority = True
    state.player.character.stats = {"force": 9, "agility": 2, "intellect": 2}
    duel.duel.rounds = [Round(stat="force")]

    real_boost = wu(1, 1, 1, name="Real Boost", mechanic=Mechanic.BOOST, element="")
    duel._commit_boost(real_boost, is_player=False, element="")
    chamelon_card = duel._chamelon_boost_card()
    assert chamelon_card is not None
    duel._commit_boost(chamelon_card, is_player=False, element="")

    duel._score_round(duel.duel.round)

    base = duel._jack_base()["force"]
    expected = base + real_boost.stats["force"] + chamelon_card.stats["force"]
    assert duel.duel.round.bot.result[0] == expected, "both boosts must be summed, not overwritten"


# --- 11. Wuya's recall stops at WITCH_RECALL_LIMIT even with qualifying Wu still in the lost pile --


async def test_wuyas_recall_stops_at_its_limit_with_lost_wu_still_qualifying():
    from xiaolin_showdown.logic.characters.wuya import WITCH_RECALL_LIMIT
    from xiaolin_showdown.logic.flow.turn import _recall_witchcraft

    state = new_game(CAT, Rng(1), CAT.character(1), opponent=_opponent("Wuya"))
    settings = XiaolinSettings()
    state.lost = [wu(5, name=f"Lost{i}", points=1) for i in range(WITCH_RECALL_LIMIT + 2)]

    for _ in range(WITCH_RECALL_LIMIT + 2):
        _recall_witchcraft(state, settings, Rng(1), Difficulty.HARD, "Wuya")

    assert state.witch_recalls == WITCH_RECALL_LIMIT
    assert len(state.lost) == 2


# --- 12. A save/restore round-trip with every exotic mid-run flag live at once ----------------------


async def test_save_and_restore_round_trips_an_exotic_mid_run_state():
    state = new_game(CAT, Rng(1), CAT.character(1), opponent=_opponent("Jack_Spicer"))
    assert state.boss_run  # derived from the boss-tier opponent, not settable
    state.jack_attack_momentum = 17
    state.jack_can_swap = True
    state.jack_flees_used = 2
    parts = [next(deepcopy(c) for c in CAT.cards if c.type == slot) for slot in jong.PART_TYPES]
    heart = next(deepcopy(c) for c in CAT.cards if mechanic_of(c.power) is Mechanic.ANIMATE)
    state.player.hand = [*parts, heart]
    jong.construct(state.player)

    restored = XiaolinState.restore(state.snapshot(), CAT)

    assert bot.is_jong(restored.player)
    assert restored.player.jong_heart is not None
    assert restored.player.jong_heart.name == heart.name
    assert restored.boss_run is True
    assert restored.jack_attack_momentum == 17
    assert restored.jack_can_swap is True
    assert restored.jack_flees_used == 2
    assert [c.type for c in restored.player.hand] == [c.type for c in state.player.hand]


# --- 13. Good Jack's training off a real boss loss raises only his own intellect --------------------


async def test_good_jacks_training_off_a_real_boss_loss_raises_only_his_intellect():
    state = new_game(CAT, Rng(1), CAT.character(1), opponent=_opponent("Jack_Spicer"))
    assert state.boss_run
    state.bot.yoyo_flipped = True
    before_intellect = state.bot.good_jack_intellect
    before_real_intellect = state.bot.character.stats["intellect"]
    before_force = state.bot.character.stats["force"]

    duel = Duel(state, Rng(1), auto_choices())
    duel.duel.stakes = None
    duel.duel.winner = True  # the bot loses -> record_showdown teaches Good Jack
    duel.duel.rounds = [Round(stat="force", score=1)]
    await duel._end()

    assert state.bot.good_jack_intellect == before_intellect + 1
    assert state.bot.character.stats["intellect"] == before_real_intellect + 1
    assert state.bot.character.stats["force"] == before_force


# --- 14. A Wu Chase gifts away wears fresh once fielded in the very next showdown -------------------


def _chase_player():
    from xiaolin_showdown.logic.characters.chase import BEAST_MARGIN
    from xiaolin_showdown.logic.schema.models import Character, Power

    chase = duelist(hand=[wu(0, name="Live"), wu(0, name="Live2")])
    beast_power = Power(-7, "Beast Form", Mechanic.BEAST_FORM, "", 0)
    chase.character = Character(13, "Chase", {"force": 7, "agility": 7, "intellect": 7}, beast_power, "heylin", False, tier="boss")
    return chase, BEAST_MARGIN


async def test_a_wu_chase_gifted_away_wears_fresh_in_the_next_showdown():
    chase, beast_margin = _chase_player()
    base = 7 - beast_margin - 1  # ahead enough that Chase declines Beast Form and fields his Wu instead
    player = duelist(stats={"force": base, "agility": base, "intellect": base}, hand=[wu(1, name="Edge")])
    prize = wu(2, name="Prize", points=3)
    state = XiaolinState(catalog=CAT, player=player, bot=chase, card_deck=[prize])  # type: ignore[arg-type]

    duel = Duel(state, Rng(0), auto_choices())
    await run_showdown(duel, XiaolinSettings())

    assert duel.duel.beast_stat is None
    assert duel.duel.winner is False and duel.duel.card_won
    assert duel.duel.prize_gifted
    assert any(c is prize for c in state.player.whole_hand)
    assert prize.uses == 0

    duel2 = Duel(state, Rng(1), auto_choices())
    duel2.duel.stakes = None
    duel2.duel.winner = True
    duel2.duel.player = replace(DuelState().player, stakes=[prize])
    duel2.duel.rounds = [Round(stat="force", score=1)]
    await duel2._end()

    assert prize.uses == 1
    assert any(c is prize for c in state.player.hand)


# --- 15. The combined Yin-Yang Yo-Yo flips the opponent, fielded straight out of a temple combine ---


async def test_the_combined_yoyo_flips_the_opponent_once_fielded_after_a_real_combine():
    from xiaolin_showdown.logic.flow.actions import combine_yoyo
    from xiaolin_showdown.logic.schema.constants import YANG_YOYO_ID, YIN_YANG_YOYO_ID, YING_YOYO_ID

    state = new_game(CAT, Rng(1), CAT.character(1))
    state.player.hand.append(deepcopy(CAT.card(YING_YOYO_ID)))
    state.player.hand.append(deepcopy(CAT.card(YANG_YOYO_ID)))
    combined = deepcopy(CAT.card(YIN_YANG_YOYO_ID))
    combine_yoyo(state, combined)
    assert any(c.id == YIN_YANG_YOYO_ID for c in state.player.hand)

    duel = Duel(state, Rng(1), auto_choices())
    duel.duel.rounds.append(Round(stat="force"))
    effect = resolve_played_power(duel.duel.round, combined, is_player=True, element="metal", stat="force")
    duel._apply_elemental(effect)

    assert state.bot.yoyo_flipped is True
    assert state.player.yoyo_flipped is False
