"""Xiaolin Showdown rules — catalog load, deterministic setup, and save round-trip.

No TTY, no textual: the game's logic layer is exercised directly. The final test proves
the real game state persists through the engine's generic SaveManager — the contract that
makes XS a cartridge the engine can save.
"""

from __future__ import annotations

from termcade.core.rng import Rng
from termcade.core.saves import SaveManager, SqliteBackend

from xiaolin_showdown.logic.actions import can_deposit, deposit
from xiaolin_showdown.logic.bot import choose_background, choose_card, choose_challenge
from xiaolin_showdown.logic.catalog import load_catalog
from xiaolin_showdown.logic.mechanics import count_end_stats, initiative
from xiaolin_showdown.logic.models import Card, Character, Player, Power
from xiaolin_showdown.logic.settings import XiaolinSettings
from xiaolin_showdown.logic.setup import new_game
from xiaolin_showdown.logic.state import XiaolinState


def _omi(catalog):
    return catalog.character(1)  # Omi — power id -1, so he carries one inalienable card


def _player_with_initiative(*bonuses: int) -> Player:
    """A Player whose hand contributes the given initiative bonuses (nothing else matters)."""
    stats = {"force": 0, "agility": 0, "intellect": 0}
    character = Character(0, "", dict(stats), Power(0, "", "hand", 0, ""), "xiaolin", True)
    hand = [
        Card(0, "", dict(stats), Power(0, "", "hand", 0, "", bonus), "metal", "item", 0)
        for bonus in bonuses
    ]
    return Player(character=character, hand=hand)


def test_catalog_loads_all_tables():
    cat = load_catalog()
    assert len(cat.powers) == 25
    assert len(cat.cards) == 25
    assert len(cat.characters) == 7
    assert cat.character(1).name == "Omi"
    assert cat.opponent_characters  # the bot must have someone to be


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
    assert len(state.card_deck) == 20 - (4 + 5)


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


def _card(force, agility, intellect, element="metal", *, trigger="hand", effect=0):
    stats = {"force": force, "agility": agility, "intellect": intellect}
    return Card(0, "", stats, Power(0, "", trigger, effect, ""), element, "wudai", 0)


_NO_STATS = {"force": 0, "agility": 0, "intellect": 0}
_STATS = ["force", "agility", "intellect"]
_ELEMENTS = ["water", "fire", "wind", "earth", "metal"]


def test_bot_picks_the_challenge_where_it_is_strongest():
    strong_force = {"force": 5, "agility": 1, "intellect": 1}
    hand = [_card(3, 0, 0)]  # a card that boosts force
    assert choose_challenge(strong_force, _STATS, hand, _NO_STATS, Rng(1)) == "force"


def test_bot_plays_the_strongest_card_for_the_challenge():
    weak, strong = _card(1, 0, 0), _card(5, 0, 0)
    chosen = choose_card(_NO_STATS, "force", "metal", [weak, strong], _NO_STATS, Rng(1))
    assert chosen is strong


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


def test_serpents_tail_play_card_cancels_the_elemental_bonus():
    queue = [_card(0, 0, 0, "water"), _card(0, 0, 0, "water", trigger="play", effect=-1)]
    # without the cancel this would be 2 * (1 + 1) = 4; the play/−1 card forces it to 0
    assert count_end_stats("force", 2, queue, _NO_STATS, "water") == 0


def test_deposit_cashes_a_card_for_its_points():
    cat = load_catalog()
    state = new_game(cat, Rng(1), _omi(cat))
    card = state.player.hand[0]
    points_before = state.player.points

    deposit(state, card)

    assert state.player.points == points_before + card.points
    assert card not in state.player.hand
    assert state.deposit_counter == 1


def test_can_deposit_respects_the_turn_limit():
    cat = load_catalog()
    state = new_game(cat, Rng(1), _omi(cat))
    assert can_deposit(state, 1) is True
    state.deposit_counter = 1
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
