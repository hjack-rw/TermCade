"""choose_card/_after playing STEAL, CONDUCT and SEIZE_GROUND for their effect, not just their
printed stats — the gap this project's own comments used to call out by name.

CONDUCT is folded straight into `_after`'s trial score: its swing is derivable purely from what's
already on the table, including a Shard fielded earlier in the same multi-Wu battle. STEAL/
SEIZE_GROUND have no in-battle stat value at all — `choose_card` prefers a live one over the
stat-best pick only when doing so doesn't cost the battle OR the decisive-blow prize the stat-best
pick would have claimed.

HACK (Denshi Bunny) is deliberately absent — checked, not built: its whole value is denying Jack a
bot identity, and Jack is never player-selectable (`is_playable=0`), so the bot can never face him as
an opponent and a "prefer HACK" heuristic would have no live trigger. SET_ARENA (Monsoon Sandals)
stays untouched too: the bot never actually chooses an element for a card that asks for one (see
`Duel._resolve_bot`), so simulating its own recolour would be a no-op today.
"""

from __future__ import annotations

from termcade.core.rng import Rng

from factories import ground, wu

from xiaolin_showdown.logic import bot as bot_module
from xiaolin_showdown.logic.battle import Round
from xiaolin_showdown.logic.bot import choose_card
from xiaolin_showdown.logic.mechanics.powers import Mechanic

FULL = {"force": 0, "agility": 0, "intellect": 0}


def _stats(**over: int) -> dict[str, int]:
    return {**FULL, **over}


# --- CONDUCT: folded into _after's own trial score ------------------------------------------------


def test_shard_of_lightning_is_valued_for_its_own_metal_swing():
    """0/0/0 alone never wins a battle — but the metal already on the table (itself included) lifts
    the contested stat enough to flip the result against a plain stat stick."""
    battle = Round(stat="force")
    battle.bot.queue.append(wu(0, 0, 0, name="Bot metal A"))
    battle.bot.queue.append(wu(0, 0, 0, name="Bot metal B"))
    battle.player.queue.append(wu(0, 0, 0, name="Player metal A"))
    shard = wu(0, 0, 0, mechanic=Mechanic.CONDUCT, name="Shard of Lightning")
    ordinary = wu(1, 0, 0, name="Ordinary")

    picked = choose_card(battle, ground(background="metal"), [shard, ordinary], Rng(1), is_player=True)

    assert picked is shard


def test_a_non_metal_table_can_turn_the_conductor_against_its_own_caster():
    """The swing is uncapped either way — a non-metal-heavy field can make it the WORSE pick."""
    battle = Round(stat="force")
    battle.bot.queue.append(wu(0, 0, 0, element="water", name="Bot water A"))
    battle.bot.queue.append(wu(0, 0, 0, element="fire", name="Bot fire A"))
    shard = wu(0, 0, 0, mechanic=Mechanic.CONDUCT, name="Shard of Lightning")
    ordinary = wu(1, 0, 0, name="Ordinary")

    picked = choose_card(battle, ground(background="water"), [shard, ordinary], Rng(1), is_player=True)

    assert picked is ordinary


def test_an_already_active_shard_still_reads_the_new_candidates_own_element():
    """A Shard fielded in an EARLIER exchange this same battle stays active for the rest of it — and
    a later, non-CONDUCT candidate's own element still shifts its already-running swing."""
    battle = Round(stat="force")
    battle.conduct_caster = True
    battle.player.queue.append(wu(0, 0, 0, mechanic=Mechanic.CONDUCT, name="Shard of Lightning"))
    metal_candidate = wu(0, 0, 0, name="Metal filler")
    water_candidate = wu(0, 0, 0, element="water", name="Water filler")

    picked = choose_card(
        battle, ground(background="water"), [water_candidate, metal_candidate], Rng(1), is_player=True
    )

    assert picked is metal_candidate


def test_an_already_active_shard_adds_only_the_new_cards_own_share_not_the_whole_net_again():
    """`Duel._ground()` bakes the swing so far into its own `player_stats` every cycle — passed in
    here as `baked`'s force=10, standing in for that. Only the CANDIDATE's own +-1 share (this
    card's element, doubled by nothing — the blow is the raw stat, not the weighted score) should
    land on top of it. The old, buggy version recomputed the WHOLE table's net a second time and
    added THAT on top of the already-baked value instead — inflating the blow past the real total.
    """
    battle = Round(stat="force")
    battle.conduct_caster = True
    battle.player.queue.append(wu(0, 0, 0, mechanic=Mechanic.CONDUCT, name="Shard of Lightning"))
    baked = ground(background="metal", player_stats=_stats(force=10))

    _, metal_blow = bot_module._after(battle, baked, wu(0, 0, 0, name="Metal filler"), is_player=True)
    _, water_blow = bot_module._after(
        battle, baked, wu(0, 0, 0, element="water", name="Water filler"), is_player=True
    )

    assert -metal_blow == 11  # 10 (already baked) + 1 (this card's own metal share)
    assert -water_blow == 9  # 10 (already baked) - 1 (this card's own non-metal share)


# --- STEAL: a fair trade, gated by the battle and the decisive-blow prize --------------------------


def test_steal_is_preferred_when_it_costs_nothing():
    battle = Round(stat="force")
    dominant = ground(bot_stats=_stats(force=50, agility=50, intellect=50))
    steal = wu(2, 0, 2, mechanic=Mechanic.STEAL, name="Sands of Time")
    strong = wu(5, 5, 5, name="Strong")

    picked = choose_card(battle, dominant, [steal, strong], Rng(1), is_player=False)

    assert picked is steal


def test_steal_never_costs_a_battle_it_would_otherwise_win():
    battle = Round(stat="force")
    tight = ground(bot_stats=_stats(), player_stats=_stats(force=5))
    steal = wu(2, 0, 2, mechanic=Mechanic.STEAL, name="Sands of Time")
    strong = wu(8, 0, 0, name="Strong")

    picked = choose_card(battle, tight, [steal, strong], Rng(1), is_player=False)

    assert picked is strong


def test_steal_never_gives_up_a_decisive_blow_prize_the_battle_was_still_won():
    """Both cards leave the bot tied on the overall battle score (the player's intellect lead cancels
    Sands of Time's own free stat win) — so the tie is broken by the blow, and ONLY strong's clears
    the decisive bar (default 8). Giving that up for Sands of Time's steal would cost the prize."""
    battle = Round(stat="force")
    tight = ground(bot_stats=_stats(force=1), player_stats=_stats(intellect=5))
    steal = wu(2, 0, 2, mechanic=Mechanic.STEAL, name="Sands of Time")
    strong = wu(7, 0, 0, name="Strong")

    picked = choose_card(battle, tight, [steal, strong], Rng(1), is_player=False)

    assert picked is strong


# --- SEIZE_GROUND: only worth taking when the acting side doesn't already hold it ------------------


def test_seize_ground_is_preferred_when_the_bot_does_not_hold_it():
    battle = Round(stat="force")
    dominant = ground(
        bot_stats=_stats(force=50, agility=50, intellect=50), challenger_is_player=True
    )
    seize = wu(2, 1, 0, mechanic=Mechanic.SEIZE_GROUND, name="Cube of Haniku")
    strong = wu(5, 5, 5, name="Strong")

    picked = choose_card(battle, dominant, [seize, strong], Rng(1), is_player=False)

    assert picked is seize


def test_seize_ground_is_not_preferred_when_the_bot_already_holds_it():
    battle = Round(stat="force")
    dominant = ground(
        bot_stats=_stats(force=50, agility=50, intellect=50), challenger_is_player=False
    )
    seize = wu(2, 1, 0, mechanic=Mechanic.SEIZE_GROUND, name="Cube of Haniku")
    strong = wu(5, 5, 5, name="Strong")

    picked = choose_card(battle, dominant, [seize, strong], Rng(1), is_player=False)

    assert picked is strong
