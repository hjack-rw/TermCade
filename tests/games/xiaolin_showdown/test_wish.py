"""Treasurebox of the Blind Sword (WISH): one wish, chosen by where it is used, then gone for good.

Deposit it for its points, spend it to wish a Wu back from the Vault, or field it to win the showdown
outright — and after any of the three it is exiled: no pile holds it, no power brings it back.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from termcade.core.rng import Rng

from card_ids import DRAW, WISH
from factories import auto_choices, plain_wu, run_showdown, wu

from xiaolin_showdown.logic.flow import temple_ai
from xiaolin_showdown.logic.flow.actions import deposit, usable_powers, use_power
from xiaolin_showdown.logic.schema.catalog import load_catalog
from xiaolin_showdown.logic.flow.duel import Duel
from xiaolin_showdown.logic.mechanics.powers import Mechanic, mechanic_of
from xiaolin_showdown.logic.flow.setup import new_game
from xiaolin_showdown.logic.config.settings import XiaolinSettings

DEFAULT = XiaolinSettings()
PLAIN_WU = plain_wu(load_catalog()).id


def _has_wish(cards):
    return any(mechanic_of(c.power) is Mechanic.WISH for c in cards)


def _seed_box(state):
    box = deepcopy(state.catalog.card(WISH))
    state.player.hand.append(box)
    return box


# --- the Vault, and depositing ----------------------------------------------------


def test_a_deposit_enters_the_vault(state):
    victim = next(c for c in state.player.hand if mechanic_of(c.power) is not Mechanic.WISH)
    deposit(state, victim, rng=Rng(1))
    assert any(c.id == victim.id for c in state.player.vault)


def test_depositing_a_treasurebox_exiles_it_rather_than_vaulting_it(state):
    deposit(state, _seed_box(state), rng=Rng(1))
    assert not _has_wish(state.player.vault)  # a Treasurebox is never restorable, even from a deposit


def test_depositing_a_treasurebox_still_pays_its_points(state):
    before = state.player.points
    deposit(state, _seed_box(state), rng=Rng(1))
    assert state.player.points == before + 10


# --- the temple wish: restore from the Vault --------------------------------------


def test_a_wish_restores_a_vaulted_wu_to_hand(state):
    box = _seed_box(state)
    state.player.vault.append(deepcopy(state.catalog.card(PLAIN_WU)))
    use_power(state, box, DEFAULT, is_player=True, target=state.player.vault[0], rng=Rng(1))
    assert any(c.id == PLAIN_WU for c in state.player.hand)


def test_a_wish_steals_a_wu_from_the_opponents_vault(state):
    """The strong wish: reach into the opponent's Vault and take a Wu they had deposited."""
    box = _seed_box(state)
    stolen = deepcopy(state.catalog.card(PLAIN_WU))
    state.bot.vault.append(stolen)
    use_power(state, box, DEFAULT, is_player=True, target=stolen, rng=Rng(1))
    assert any(c.id == PLAIN_WU for c in state.player.hand)
    assert not state.bot.vault  # taken from them


def test_the_treasurebox_name_runs_through_the_five_element_colours(state):
    from xiaolin_showdown.screens.display.format import COLORS, card_name_text

    text = card_name_text(deepcopy(state.catalog.card(WISH)))
    styles = " ".join(span.style for span in text.spans)
    assert all(hex_colour in styles for hex_colour in COLORS.values())


def test_a_spent_treasurebox_is_exiled_not_sent_to_the_used_pile(state):
    box = _seed_box(state)
    state.player.vault.append(deepcopy(state.catalog.card(PLAIN_WU)))
    use_power(state, box, DEFAULT, is_player=True, target=state.player.vault[0], rng=Rng(1))
    assert not _has_wish(state.player.whole_hand)
    assert not _has_wish(state.used)  # gone for good — a Refresh cannot call it back


def test_the_treasurebox_is_hidden_with_an_empty_vault(state):
    _seed_box(state)
    assert not [c for c in usable_powers(state, 3, DEFAULT) if mechanic_of(c.power) is Mechanic.WISH]


# --- the duel wish: field it to win -----------------------------------------------


def _duel_where_the_player_fields_the_box():
    cat = load_catalog()
    rng = Rng(1)
    state = new_game(cat, rng, cat.character(1))
    state.player.hand = [deepcopy(cat.card(WISH)), deepcopy(cat.card(PLAIN_WU))]
    state.forced_priority = True  # the player leads and names the challenge

    async def _play_the_box(playable):
        return next((c for c in playable if c.id == WISH), playable[0])

    choices = replace(auto_choices(), card=_play_the_box)
    return state, Duel(state, rng, choices)


async def test_fielding_a_treasurebox_wins_the_showdown_outright():
    state, duel = _duel_where_the_player_fields_the_box()
    await run_showdown(duel, XiaolinSettings())
    assert duel.duel.winner is True  # 0/0/0 on the board, but the wish wins regardless


async def test_a_fielded_treasurebox_is_exiled_when_the_showdown_ends():
    state, duel = _duel_where_the_player_fields_the_box()
    await run_showdown(duel, XiaolinSettings())
    assert not _has_wish(state.player.whole_hand)
    assert not _has_wish(state.lost) and not _has_wish(state.used)


# --- the bot plays it too (no throwing away the strongest card) -------------------


def test_the_bot_fields_a_treasurebox_over_anything_scored_on_stats():
    from factories import ground

    from xiaolin_showdown.logic.flow.battle import Round
    from xiaolin_showdown.logic.flow.bot import choose_card

    cat = load_catalog()
    box = deepcopy(cat.card(WISH))
    fist = deepcopy(cat.card(PLAIN_WU))
    chosen = choose_card(Round(stat="force"), ground(), [fist, box], Rng(1))
    assert mechanic_of(chosen.power) is Mechanic.WISH  # the auto-win, not the 1/1/1


def test_the_bot_never_banks_a_treasurebox():
    from termcade.core.settings import Difficulty

    from xiaolin_showdown.logic.flow.turn import pick_deposit

    cat = load_catalog()
    hand = [deepcopy(cat.card(WISH)), deepcopy(cat.card(DRAW))]  # worth points
    banked = pick_deposit(hand, Difficulty.HARD, DEFAULT.wear_limit)
    assert banked is not None and mechanic_of(banked.power) is not Mechanic.WISH


# --- the temple wish's bot policy: spend it on the single best Wu either Vault holds --------------


def test_worth_wishing_declines_with_both_vaults_empty(state):
    assert temple_ai._worth_wishing(state, is_player=False) is False


def test_worth_wishing_fires_on_a_strong_wu_in_the_bots_own_vault(state):
    state.bot.vault.append(wu(3, 3, 3, name="Strong", id=1))
    assert temple_ai._worth_wishing(state, is_player=False) is True


def test_worth_wishing_declines_on_a_weak_vault(state):
    state.bot.vault.append(wu(1, 0, 0, name="Weak", id=1))
    assert temple_ai._worth_wishing(state, is_player=False) is False


def test_worth_wishing_fires_on_a_strong_wu_in_the_opponents_vault(state):
    """Reaching into the opponent's Vault is the card's real strength, not just its own."""
    state.player.vault.append(wu(3, 3, 3, name="Strong", id=1))
    assert temple_ai._worth_wishing(state, is_player=False) is True


def test_best_wishable_picks_the_stronger_wu_across_both_vaults(state):
    weak = wu(1, 0, 0, name="Weak", id=1)
    strong = wu(3, 3, 3, name="Strong", id=2)
    state.bot.vault.append(weak)
    state.player.vault.append(strong)
    assert temple_ai._best_wishable(state, is_player=False) is strong


def test_choose_temple_power_wishes_for_the_best_vault_wu(state):
    box = deepcopy(state.catalog.card(WISH))
    state.bot.hand = [box]
    target = wu(3, 3, 3, name="Strong", id=1)
    state.player.vault.append(target)
    play = temple_ai.choose_temple_power(state, DEFAULT, is_player=False)
    assert play is not None
    assert play.card.id == box.id
    assert play.target is target


def test_choose_temple_power_does_not_wish_on_an_empty_vault(state):
    box = deepcopy(state.catalog.card(WISH))
    state.bot.hand = [box]
    play = temple_ai.choose_temple_power(state, DEFAULT, is_player=False)
    assert play is None or mechanic_of(play.card.power) is not Mechanic.WISH
