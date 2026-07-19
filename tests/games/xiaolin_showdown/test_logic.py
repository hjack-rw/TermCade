"""Xiaolin Showdown rules — catalog load, deterministic setup, and save round-trip.

No TTY, no textual: the game's logic layer is exercised directly. The final test proves
the real game state persists through the engine's generic SaveManager — the contract that
makes XS a cartridge the engine can save.
"""

from __future__ import annotations

from copy import deepcopy

from termcade.core.rng import Rng
from termcade.core.saves import SaveManager, SqliteBackend

from xiaolin_showdown.logic.actions import (
    FIZZLE_MESSAGE,
    can_deposit,
    can_draw,
    deposit,
    draw,
    swap_from_hand,
    usable_powers,
    use_power,
)
from xiaolin_showdown.logic.battle import Ground, Round
from xiaolin_showdown.logic.bot import choose_background, choose_boost, choose_card, choose_challenge
from xiaolin_showdown.logic.mechanics.resolve import resolve_played_power
from xiaolin_showdown.logic.catalog import load_catalog
from xiaolin_showdown.logic.mechanics.scoring import count_end_stats, initiative
from xiaolin_showdown.logic.models import Card, Mechanic, Player, Power
from xiaolin_showdown.logic.outcome import final_score
from xiaolin_showdown.logic.settings import XiaolinSettings, deck_size_for, point_limit_for
from xiaolin_showdown.logic.setup import new_game
from xiaolin_showdown.logic.state import XiaolinState
from factories import duelist, wu


def _omi(catalog):
    return catalog.character(1)  # Omi — power id -1, so he carries one inalienable card


def _player_with_initiative(*bonuses: int) -> Player:
    """A Player whose hand contributes the given initiative bonuses (nothing else matters)."""
    hand = [wu(mechanic=Mechanic.INITIATIVE, bonus=bonus, name="") for bonus in bonuses]
    return duelist(hand=hand, name="")


def test_catalog_loads_all_tables():
    cat = load_catalog()
    assert cat.powers and cat.cards
    assert len(cat.characters) == 11  # 4 playable + easy 3 + hard 3 + boss 1
    assert cat.character(1).name == "Omi"
    assert cat.opponent_characters  # the bot must have someone to be


def test_settings_defaults_match_the_card_pool():
    """A bare ``XiaolinSettings()`` deals a real game, so its literals must say what the pool says.

    Left stale, ``max_deck_size`` shuffles the pool and truncates it — the newest Wu sit out of the
    run at random, while ``point_limit`` still counts the points they took with them. Print a Wu,
    and this is the test that tells you the two numbers moved.
    """
    cards = load_catalog().cards
    shipped = XiaolinSettings()

    assert shipped.max_deck_size == deck_size_for(cards)
    assert shipped.point_limit == point_limit_for(cards)


def test_card_ids_are_contiguous_from_zero():
    """``new_game`` deals the pile by indexing the card list with an id. A gap deals the wrong Wu,
    and a beginning Wu is found by ``id == abs(power_id)`` — so a hole is silent corruption, not a
    missing card. Guards the seed, where a new Wu is written by hand."""
    cat = load_catalog()

    assert [card.id for card in cat.cards] == list(range(len(cat.cards)))


def test_new_game_is_deterministic_for_a_seed():
    cat = load_catalog()
    a = new_game(cat, Rng(2024), _omi(cat))
    b = new_game(cat, Rng(2024), _omi(cat))
    assert [c.id for c in a.card_deck] == [c.id for c in b.card_deck]
    assert [c.id for c in a.player.hand] == [c.id for c in b.player.hand]
    assert a.bot.character.id == b.bot.character.id
    # A different seed reorders the 20-card pile (collision negligible).
    other = new_game(cat, Rng(9999), _omi(cat))
    assert [c.id for c in other.card_deck] != [c.id for c in a.card_deck]


def test_new_game_hand_sizes():
    cat = load_catalog()
    state = new_game(cat, Rng(1), _omi(cat))
    assert len(state.player.hand) == 4  # 5 minus the inalienable card
    assert len(state.player.inalienable_hand) == 1
    assert len(state.bot.hand) == 5
    assert len(state.card_deck) == XiaolinSettings().max_deck_size - (4 + 5)


def test_snapshot_round_trips_through_savemanager(tmp_path):
    cat = load_catalog()
    rng = Rng("duel-seed")
    state = new_game(cat, rng, _omi(cat))
    state.player.points = 7  # progress accrued between duels

    mgr = SaveManager("xiaolin_showdown", SqliteBackend(tmp_path / "saves.db"))
    mgr.save(0, state, rng, title="mid-run")
    loaded, _loaded_rng, meta, _settings = mgr.load(0, XiaolinState, ctx=None)

    assert isinstance(loaded, XiaolinState)
    assert loaded.player.points == 7
    assert [c.id for c in loaded.player.hand] == [c.id for c in state.player.hand]
    assert [c.id for c in loaded.player.inalienable_hand] == [
        c.id for c in state.player.inalienable_hand
    ]
    assert [c.id for c in loaded.card_deck] == [c.id for c in state.card_deck]
    assert loaded.player.character.id == state.player.character.id
    assert loaded.bot.character.id == state.bot.character.id
    assert meta.schema_version == state.schema_version


def _card(force, agility, intellect, element="metal", *, mechanic=Mechanic.PRINTED_STATS):
    return wu(force, agility, intellect, element=element, mechanic=mechanic, name="", type="wudai")


_NO_STATS = {"force": 0, "agility": 0, "intellect": 0}
_STATS = ["force", "agility", "intellect"]
_ELEMENTS = ["water", "fire", "wind", "earth", "metal"]
_NO_POWER = Power(0, "", Mechanic.FILLER, "")


def test_bot_picks_the_challenge_where_it_is_strongest():
    strong_force = {"force": 5, "agility": 1, "intellect": 1}
    hand = [_card(3, 0, 0)]  # a card that boosts force
    assert choose_challenge(strong_force, _STATS, hand, _NO_STATS, Rng(1)) == "force"


def _ground(stat: str = "force", background: str = "metal") -> Ground:
    return Ground(
        stats=list(_STATS), background=background, player_stats=_NO_STATS, bot_stats=_NO_STATS
    )


def test_bot_plays_the_strongest_card_for_the_challenge():
    weak, strong = _card(1, 0, 0), _card(5, 0, 0)
    chosen = choose_card(Round(stat="force"), _ground(), [weak, strong], Rng(1))
    assert chosen is strong


def test_bot_answers_the_wu_already_on_the_ground():
    """The bot fields second, so the player's Wu is on the board when it chooses.

    Scoring a card in isolation cannot tell a Wu that wins the battle from one that loses it: here
    the bigger Wu on the wrong stat loses, and only reading the ground says so.
    """
    battle = Round(stat="force")
    resolve_played_power(battle, _card(4, 0, 0), is_player=True, element="metal")

    loses_force, wins_force = _card(0, 9, 0), _card(5, 0, 0)
    chosen = choose_card(battle, _ground(), [loses_force, wins_force], Rng(1))

    assert chosen is wins_force, "the bot took the bigger number and lost the stat that counts"


def test_bot_declines_a_boost_that_buys_it_nothing():
    """Boosting out of hand costs the Wu it would have been, so it must earn its place."""
    battle = Round(stat="force")
    dud = _card(0, 0, 0, mechanic=Mechanic.BOOST)
    winner = _card(5, 0, 0)

    # already winning on every stat: a boost cannot improve a battle that is already won
    resolve_played_power(battle, _card(0, 0, 0), is_player=True, element="metal")
    chosen = choose_boost(battle, _ground(), [], [winner, dud])

    assert chosen is None


def test_bot_background_favours_its_own_boosting_element():
    strong_force = {"force": 5, "agility": 0, "intellect": 0}
    bot_hand = [_card(3, 0, 0, "water")]
    player_hand = [_card(0, 0, 0, "fire")]
    chosen = choose_background(strong_force, _ELEMENTS, (bot_hand, player_hand), _NO_STATS, Rng(1))
    assert chosen == "water"


def test_count_end_stats_adds_base_and_queued_card_stats():
    queue = [_card(2, 0, 0), _card(3, 0, 0)]
    char = {"force": 5, "agility": 5, "intellect": 2}
    assert count_end_stats("force", 0, queue, char, "metal") == 5 + 2 + 3


def test_count_end_stats_counts_none_stats_as_zero():
    queue = [_card(None, None, None)]  # a non-combat card
    assert count_end_stats("force", 0, queue, {"force": 3, "agility": 0, "intellect": 0}, "metal") == 3


def test_count_end_stats_absolute_false_ignores_negatives():
    queue = [_card(-4, 0, 0)]
    char = {"force": 5, "agility": 0, "intellect": 0}
    assert count_end_stats("force", 0, queue, char, "metal", absolute=True) == 1
    assert count_end_stats("force", 0, queue, char, "metal", absolute=False) == 5


def test_count_end_stats_elemental_bonus_rewards_match_penalises_opposite():
    same = [_card(0, 0, 0, "water")]
    opposite = [_card(0, 0, 0, "fire")]  # fire is water's opposite
    assert count_end_stats("force", 2, same, _NO_STATS, "water") == 2
    assert count_end_stats("force", 2, opposite, _NO_STATS, "water") == -2


def test_count_end_stats_does_not_inspect_powers():
    """Whether the elemental bonus applies is the caller's call (see `DuelState`).

    This used to scan the queue for a `play`/-1 card — a state the duel never produces, since a
    played card enters as a stand-in wearing a neutral power. The scan was dead, and the test that
    covered it built a queue by hand.
    """
    tail = _card(0, 0, 0, "water", mechanic=Mechanic.INTANGIBLE)
    assert count_end_stats("force", 2, [tail], _NO_STATS, "water") == 2


def test_deposit_cashes_a_card_for_its_points():
    cat = load_catalog()
    state = new_game(cat, Rng(1), _omi(cat))
    card = state.player.hand[0]
    points_before = state.player.points

    deposit(state, card, rng=Rng(1))

    assert state.player.points == points_before + card.points
    assert card not in state.player.hand
    assert state.actions_taken == 1


def test_can_deposit_respects_the_turn_limit():
    cat = load_catalog()
    state = new_game(cat, Rng(1), _omi(cat))
    assert can_deposit(state, 1) is True
    state.actions_taken = 1
    assert can_deposit(state, 1) is False


def test_initiative_keeps_own_positives_and_inherits_opponent_negatives():
    player = _player_with_initiative(2, 3, -1)  # own +2, +3 count; own -1 does not
    bot = _player_with_initiative(5, -4)  # own +5 counts; its -4 flows to the player

    player_init, bot_init = initiative(player, bot)

    assert player_init == 2 + 3 - 4  # own positives + opponent's negatives
    assert bot_init == 5 - 1


def test_custom_settings_drive_the_deal():
    cat = load_catalog()
    custom = XiaolinSettings(starting_hand_player=3, starting_hand_bot=2, max_deck_size=12)
    state = new_game(cat, Rng(1), _omi(cat), settings=custom)
    assert len(state.player.hand) == 2  # 3 minus Omi's inalienable card
    assert len(state.bot.hand) == 2
    assert len(state.card_deck) == 12 - (2 + 2)


def test_custom_settings_freeze_into_the_save(tmp_path):
    cat = load_catalog()
    rng = Rng("ruled")
    custom = XiaolinSettings(point_limit=20, starting_hand_player=3)
    state = new_game(cat, rng, _omi(cat), settings=custom)

    mgr = SaveManager("xiaolin_showdown", SqliteBackend(tmp_path / "saves.db"))
    mgr.save(0, state, rng, title="custom", settings=custom.to_settings())
    _state, _rng, _meta, loaded = mgr.load(0, XiaolinState, ctx=None)

    restored = XiaolinSettings.from_settings(loaded)
    assert restored.point_limit == 20
    assert restored.starting_hand_player == 3


def test_settings_clamp_impossible_values_to_a_playable_range():
    # Whatever a player types on the Settings screen, a game must still be dealable.
    s = XiaolinSettings(
        max_hand_size=0,
        starting_hand_player=0,
        starting_hand_bot=0,
        max_deck_size=1,
        point_limit=0,
        starting_points_player=99,
        actions_per_turn=0,
    )
    assert s.max_hand_size == 1
    assert s.starting_hand_player == 1 and s.starting_hand_bot == 1
    assert s.point_limit == 2
    assert s.starting_points_player == s.point_limit - 1  # capped below the point limit
    assert s.actions_per_turn == 1
    assert s.max_deck_size >= s.starting_hand_player + s.starting_hand_bot + 1  # deck fits both hands


def test_final_score_cashes_leftover_hand_cards_when_the_pile_is_empty():
    cat = load_catalog()
    state = new_game(cat, Rng(1), _omi(cat))
    state.player.points = 5
    state.card_deck.clear()  # the pile ran dry — hand cards now count
    hand_points = sum(card.points for card in state.player.whole_hand)

    assert final_score(state, Rng(1)).player_points == 5 + hand_points


def test_final_score_ignores_hand_cards_while_the_pile_still_has_cards():
    cat = load_catalog()
    state = new_game(cat, Rng(1), _omi(cat))
    state.player.points = 9  # a point-limit ending: the pile is not empty, so hands are not counted

    assert final_score(state, Rng(1)).player_points == 9


def test_final_score_names_the_higher_scoring_duelist():
    cat = load_catalog()
    state = new_game(cat, Rng(1), _omi(cat))
    state.player.points = 5  # pile still full, so bot stays at 0

    assert final_score(state, Rng(1)).winner is state.player.character


def test_final_score_reports_a_tie_when_points_are_level():
    cat = load_catalog()
    state = new_game(cat, Rng(1), _omi(cat))  # both at 0, pile full

    assert final_score(state, Rng(1)).winner is None


def _named(cat, name: str) -> Card:
    return deepcopy(next(card for card in cat.cards if card.name == name))


def test_use_power_draws_a_wu_and_banks_no_points():
    cat = load_catalog()
    state = new_game(cat, Rng(1), _omi(cat))
    bras = _named(cat, "Bras Finger")  # deposit/+1 — Chronokinesis draws a card
    state.player.hand.append(bras)
    hand_size, deck_before = len(state.player.hand), len(state.card_deck)
    drawn = state.card_deck[0]  # Chronokinesis takes the top of the pile — read its name off the card

    message = use_power(state, bras)

    assert message.log == f"You drew {drawn.name}."  # cast by the player, so the log reads "You"
    assert all(card is not bras for card in state.player.hand)  # spent, not banked
    assert len(state.player.hand) == hand_size  # a drawn Wu replaced it
    assert len(state.card_deck) == deck_before - 1
    assert state.player.points == 0  # using a power never gives points


def test_use_power_on_the_gag_wu_fizzles_for_no_points():
    cat = load_catalog()
    state = new_game(cat, Rng(1), _omi(cat))
    ohwah = _named(cat, "Ohwah Tegu Saim")  # deposit/0 — the "? ? ?" gag power
    state.player.hand.append(ohwah)
    deck_before = len(state.card_deck)

    message = use_power(state, ohwah)

    assert message == FIZZLE_MESSAGE
    assert all(card is not ohwah for card in state.player.hand)  # discarded
    assert len(state.card_deck) == deck_before  # nothing drawn
    assert state.player.points == 0  # unlike depositing it, which would bank its point


def test_draw_pulls_a_wu_from_the_personal_deck_into_the_hand():
    cat = load_catalog()
    state = new_game(cat, Rng(1), _omi(cat))
    shelved = deepcopy(cat.card(6))
    state.player.deck.append(shelved)
    hand_before = len(state.player.hand)

    drawn = draw(state)

    assert drawn is shelved
    assert any(card is shelved for card in state.player.hand)
    assert len(state.player.hand) == hand_before + 1
    assert not state.player.deck
    assert state.actions_taken == 1


def test_can_draw_respects_the_turns_one_action():
    cat = load_catalog()
    state = new_game(cat, Rng(1), _omi(cat))
    settings = XiaolinSettings()
    state.player.deck.append(deepcopy(cat.card(6)))  # a Wu waiting to be drawn, hand has room

    assert can_draw(state, settings) is True
    state.actions_taken = settings.actions_per_turn  # this turn's draw is spent
    assert can_draw(state, settings) is False


def test_swapping_from_a_full_hand_keeps_it_the_same_size_and_costs_the_action():
    cat = load_catalog()
    state = new_game(cat, Rng(1), _omi(cat))
    shelved = state.player.hand[0]
    state.player.deck.append(deepcopy(cat.card(6)))  # something to draw back
    hand_before = len(state.player.hand)

    drawn = swap_from_hand(state, shelved, rng=Rng(1))

    assert len(state.player.hand) == hand_before  # net size unchanged
    assert all(card is not shelved for card in state.player.hand)  # the chosen Wu left the hand
    assert any(card is drawn for card in state.player.hand)  # a Wu came back
    assert state.actions_taken == 1  # for the one action


def test_usable_powers_respect_the_turns_one_action():
    cat = load_catalog()
    state = new_game(cat, Rng(1), _omi(cat))
    bras = _named(cat, "Bras Finger")
    state.player.hand.append(bras)

    assert any(card is bras for card in usable_powers(state, actions_per_turn=1))
    state.actions_taken = 1  # the turn's deposit is spent → the deposit Wu is no longer usable
    assert all(card is not bras for card in usable_powers(state, actions_per_turn=1))


def test_the_opponent_rosters_are_disjoint():
    catalog = load_catalog()
    easy = {c.id for c in catalog.opponents("easy")}
    hard = {c.id for c in catalog.opponents("hard")}
    boss = {c.id for c in catalog.opponents("boss")}

    assert easy and hard and boss  # every tier is populated
    assert easy.isdisjoint(hard) and easy.isdisjoint(boss) and hard.isdisjoint(boss)


def test_no_playable_character_sits_on_an_opponent_roster():
    catalog = load_catalog()
    rosters = catalog.opponents("easy") + catalog.opponents("hard") + catalog.opponents("boss")

    assert all(not c.is_playable for c in rosters)


def test_a_normal_game_never_deals_a_hard_opponent():
    catalog = load_catalog()
    omi = catalog.character(1)

    bots = {new_game(catalog, Rng(seed), omi).bot.character.id for seed in range(30)}

    assert bots <= {c.id for c in catalog.opponents("easy")}


def test_a_hard_game_only_deals_hard_opponents():
    catalog = load_catalog()
    omi = catalog.character(1)

    bots = {
        new_game(catalog, Rng(seed), omi, roster="hard").bot.character.id
        for seed in range(30)
    }

    assert bots <= {c.id for c in catalog.opponents("hard")}


def test_a_boss_game_deals_the_boss_and_grants_its_wudai():
    """The boss run deals Hannibal, and he holds Moby Morpher (card 5) inalienably — off the pile."""
    catalog = load_catalog()
    omi = catalog.character(1)

    state = new_game(catalog, Rng(7), omi, roster="boss")

    assert state.bot.character.name == "Hannibal_Roy_Bean"
    assert [c.id for c in state.bot.inalienable_hand] == [5]  # Moby Morpher, granted not drawn
    assert all(c.id != 5 for c in state.card_deck)  # reserved out of the pool

    held = state.bot.inalienable_hand[0]
    assert held.type == "wudai"  # a held signature is a wudai...
    assert catalog.card(5).type == "arms"  # ...but the pool copy keeps its printed 'arms'
    assert XiaolinState.restore(state.snapshot(), None).bot.inalienable_hand[0].type == "wudai"


# --- the elemental bonus reads two sets of cards, in opposite directions ------------


def test_a_curse_mirror_costs_you_the_bonus_it_would_have_earned_its_caster():
    """A resonant curse cast at you bites deeper: the ±1 is negated, not ignored."""
    water_curse = Card(1, "Curse", {"force": 0, "agility": 0, "intellect": 0}, _NO_POWER, "water", "item", 0)

    assert count_end_stats("force", 1, [water_curse], _NO_STATS, "water", earns_bonus=[]) == 0
    assert (
        count_end_stats("force", 1, [water_curse], _NO_STATS, "water", earns_bonus=[], suffers_bonus=[water_curse])
        == -1
    )


def test_the_same_wu_earns_the_bonus_when_you_are_the_one_who_played_it():
    """Guards the sign: identical card, opposite side of the table, opposite result."""
    water_wu = Card(1, "Wu", {"force": 0, "agility": 0, "intellect": 0}, _NO_POWER, "water", "item", 0)

    assert count_end_stats("force", 1, [water_wu], _NO_STATS, "water", earns_bonus=[water_wu]) == 1
