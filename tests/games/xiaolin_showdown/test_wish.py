"""Treasurebox of the Blind Sword (WISH): one wish, chosen by where it is used, then gone for good.

Deposit it for its points, spend it to wish a Wu back from the Vault, or field it to win the showdown
outright — and after any of the three it is exiled: no pile holds it, no power brings it back.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from termcade.core.rng import Rng

from factories import auto_choices, run_showdown

from xiaolin_showdown.logic.flow.actions import deposit, usable_powers, use_power
from xiaolin_showdown.logic.schema.catalog import load_catalog
from xiaolin_showdown.logic.flow.duel import Duel
from xiaolin_showdown.logic.mechanics.powers import Mechanic, mechanic_of
from xiaolin_showdown.logic.flow.setup import new_game
from xiaolin_showdown.logic.config.settings import XiaolinSettings

BOX = 67  # Treasurebox of the Blind Sword — wish
FIST = 6  # Fist of Tebigong — a plain Wu


def _has_wish(cards):
    return any(mechanic_of(c.power) is Mechanic.WISH for c in cards)


def _seed_box(state):
    box = deepcopy(state.catalog.card(BOX))
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
    state.player.vault.append(deepcopy(state.catalog.card(FIST)))
    use_power(state, box, is_player=True, target=state.player.vault[0], rng=Rng(1))
    assert any(c.id == FIST for c in state.player.hand)


def test_a_wish_steals_a_wu_from_the_opponents_vault(state):
    """The strong wish: reach into the opponent's Vault and take a Wu they had deposited."""
    box = _seed_box(state)
    stolen = deepcopy(state.catalog.card(FIST))
    state.bot.vault.append(stolen)
    use_power(state, box, is_player=True, target=stolen, rng=Rng(1))
    assert any(c.id == FIST for c in state.player.hand)
    assert not state.bot.vault  # taken from them


def test_the_treasurebox_name_runs_through_the_five_element_colours(state):
    from xiaolin_showdown.screens.display.format import COLORS, card_name_text

    text = card_name_text(deepcopy(state.catalog.card(BOX)))
    styles = " ".join(span.style for span in text.spans)
    assert all(hex_colour in styles for hex_colour in COLORS.values())


def test_a_spent_treasurebox_is_exiled_not_sent_to_the_used_pile(state):
    box = _seed_box(state)
    state.player.vault.append(deepcopy(state.catalog.card(FIST)))
    use_power(state, box, is_player=True, target=state.player.vault[0], rng=Rng(1))
    assert not _has_wish(state.player.whole_hand)
    assert not _has_wish(state.used)  # gone for good — a Refresh cannot call it back


def test_the_treasurebox_is_hidden_with_an_empty_vault(state):
    _seed_box(state)
    assert not [c for c in usable_powers(state, 3) if mechanic_of(c.power) is Mechanic.WISH]


# --- the duel wish: field it to win -----------------------------------------------


def _duel_where_the_player_fields_the_box():
    cat = load_catalog()
    rng = Rng(1)
    state = new_game(cat, rng, cat.character(1))
    state.player.hand = [deepcopy(cat.card(BOX)), deepcopy(cat.card(FIST))]
    state.forced_priority = True  # the player leads and names the challenge

    async def _play_the_box(playable):
        return next((c for c in playable if c.id == BOX), playable[0])

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
    box = deepcopy(cat.card(BOX))
    fist = deepcopy(cat.card(FIST))
    chosen = choose_card(Round(stat="force"), ground(), [fist, box], Rng(1))
    assert mechanic_of(chosen.power) is Mechanic.WISH  # the auto-win, not the 1/1/1


def test_the_bot_never_banks_a_treasurebox():
    from termcade.core.settings import Difficulty

    from xiaolin_showdown.logic.flow.turn import pick_deposit

    cat = load_catalog()
    hand = [deepcopy(cat.card(BOX)), deepcopy(cat.card(16))]  # Bras Finger, worth points
    banked = pick_deposit(hand, Difficulty.HARD)
    assert banked is not None and mechanic_of(banked.power) is not Mechanic.WISH
