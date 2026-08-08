"""Play full games with a COMPETENT player on both sides, and report the economy.

The old harness played the first legal card every time and won 0/400 — it could tell you a change
had happened, but nothing about whether the game was fair. This one drives the player with the same
decision functions the bot uses, so the two sides differ only in their stats and their deposit rule.
That makes the win rate mean something.

The only thing that can answer "is this fair?" — the test suite proves the rules are obeyed, not
that the game is worth playing. Every balance claim in this project's history came from here.

    python scripts/balance.py . 150

Reports, per difficulty: the player's win rate, average points, showdown count, hand sizes, which
wagers got called, and which were even fieldable. Both sides play with the same decision functions,
so the win rate means something — an earlier harness played the first legal card every time, won
0/400, and could only tell you that a change had happened, never whether it was good.
"""

import asyncio
import json
import os
import sys
from statistics import mean

REPO = sys.argv[1]
RUNS = int(sys.argv[2]) if len(sys.argv) > 2 else 200
sys.path[:0] = [REPO + "/games", REPO + "/engine"]

from termcade.core.rng import Rng  # noqa: E402
from termcade.core.settings import Difficulty, Settings  # noqa: E402
from xiaolin_showdown.logic.flow import actions, bot, temple_ai  # noqa: E402

# The bot's own constants, swept from the outside so a claim about one of them is measured, not argued.
if os.environ.get('XS_REVIVAL'):
    temple_ai.REVIVAL_MARGIN = int(os.environ['XS_REVIVAL'])
if os.environ.get('XS_WISH_MARGIN'):
    temple_ai.WISH_MARGIN = int(os.environ['XS_WISH_MARGIN'])
if os.environ.get('XS_BIRD_CEILING'):
    temple_ai.EARLY_BIRD_CEILING = int(os.environ['XS_BIRD_CEILING'])
if os.environ.get('XS_SWAP_MARGIN'):
    temple_ai.SWAP_MARGIN = int(os.environ['XS_SWAP_MARGIN'])
if os.environ.get('XS_WITCH_BIRD_GAP'):  # Wuya's Early-Bird sense: the lead she needs to fly the bird
    from xiaolin_showdown.logic.flow import actions as _actions_witch_bird
    _actions_witch_bird.WITCH_EARLY_BIRD_GAP = int(os.environ['XS_WITCH_BIRD_GAP'])
if os.environ.get('XS_BEAST_MARGIN'):
    from xiaolin_showdown.logic.characters import chase as _chase_margin
    _chase_margin.BEAST_MARGIN = int(os.environ['XS_BEAST_MARGIN'])
if os.environ.get('XS_BEAST_BOOST'):
    from xiaolin_showdown.logic.flow import duel as _duel_beast
    _duel_beast.BEAST_BOOST = int(os.environ['XS_BEAST_BOOST'])
# The random arena is now the shipped default (settings.random_background=1). XS_CHOSEN_BG=1 turns it
# OFF — the non-challenger picks the background again — for the A/B against the default. Applied per run
# in `play`, where the settings are built.
if os.environ.get('XS_WITCH_RECALL'):
    temple_ai.WITCH_RECALL_MARGIN = int(os.environ['XS_WITCH_RECALL'])
if os.environ.get('XS_WITCH_LIMIT'):
    temple_ai.WITCH_RECALL_LIMIT = int(os.environ['XS_WITCH_LIMIT'])
if os.environ.get('XS_WITCH_NOWEAR'):
    from xiaolin_showdown.logic.flow import actions as _actions_witch
    _actions_witch.WITCHCRAFT_WEARS = False
if os.environ.get('XS_WITCH_OFF'):
    from xiaolin_showdown.logic.flow import actions as _actions_woff
    _actions_woff.WITCHCRAFT_RETURNS = False
from xiaolin_showdown.logic.schema.catalog import load_catalog  # noqa: E402
from xiaolin_showdown.logic.flow.duel import Duel, DuelChoices  # noqa: E402

if os.environ.get("XS_NO_HEART_COUNTER"):  # A/B: leave the Heart of Jong's summon unanswered
    async def _no_heart_counter(self, current):  # noqa: ANN001
        return None

    Duel._offer_balance = _no_heart_counter  # type: ignore[method-assign]
from xiaolin_showdown.logic.characters import jong  # noqa: E402

if os.environ.get("XS_JONG_NO_BREAK"):  # A/B: the form never drops from a broken set (wear-out / steal)
    jong.drop_if_broken = lambda player: None  # type: ignore[assignment]  # noqa: ARG005
from xiaolin_showdown.logic.config.settings import (  # noqa: E402
    XiaolinSettings,
    player_actions,
    refreshed_for_pool,
    roster_of,
)
from xiaolin_showdown.logic.flow.setup import new_game  # noqa: E402
from xiaolin_showdown.logic.flow import setup as _setup_mod  # noqa: E402

if os.environ.get("XS_SCEN_BOSS"):  # sweep a per-boss deal-weight scenario: base/points/duel/counter
    from dataclasses import replace as _replace

    _scen_name = os.environ["XS_SCEN_BOSS"]
    _base = _setup_mod._SCENARIOS.get(_scen_name, _setup_mod._BASE_WEIGHTS)
    _overrides = {}
    if os.environ.get("XS_SCEN_BASE"):
        _overrides["base"] = int(os.environ["XS_SCEN_BASE"])
    if os.environ.get("XS_SCEN_POINTS"):
        _overrides["points"] = int(os.environ["XS_SCEN_POINTS"])
    if os.environ.get("XS_SCEN_DUEL"):
        _overrides["duel"] = int(os.environ["XS_SCEN_DUEL"])
    if os.environ.get("XS_SCEN_COUNTER"):
        _overrides["counter"] = int(os.environ["XS_SCEN_COUNTER"])
    _setup_mod._SCENARIOS[_scen_name] = _replace(_base, **_overrides)
from xiaolin_showdown.logic.flow.actions import (  # noqa: E402
    deposit,
    draw,
    early_bird,
    initiative_lead,
    train,
    use_power,
)
from xiaolin_showdown.logic.flow.training import (  # noqa: E402
    add_progress,
    can_train,
    payout_ready,
    pick_stat,
    raise_stat,
)

# (The XS_STICKY_WEAR knob is retired: per-wearer wear memory measured identical to reset-on-every-
# transfer at 200/tier and is now the SHIPPED rule — see BALANCE-HISTORY.md.)

# Sweep knob: a lost showdown teaches +N instead of +1 (XS_LOSS_FILL=2). Patched on the DUEL's
# bound name — it imported `record_showdown` at module load, so patching training alone misses it.
if os.environ.get("XS_LOSS_FILL"):
    from xiaolin_showdown.logic import duel as _duel_mod

    _FILL = int(os.environ["XS_LOSS_FILL"])

    def _record(state, *, player_won):
        loser = state.bot if player_won else state.player
        if add_progress(loser, _FILL) and loser is state.bot:
            stat = pick_stat(loser)
            raise_stat(loser, stat)
            return stat
        return None

    _duel_mod.record_showdown = _record
from xiaolin_showdown.logic.mechanics.powers import mechanic_of  # noqa: E402
from xiaolin_showdown.logic.flow.temple_ai import (  # noqa: E402
    choose_early_bird,
    choose_temple_power,
)
from xiaolin_showdown.logic.flow.turn import (  # noqa: E402
    DUEL_FLOOR,
    EARLY_BIRD,
    bot_turn,
    pick_deposit,
    refill_hands,
)

FLIGHTS = {'player': 0, 'bot': 0, 'leads': []}

from collections import Counter  # noqa: E402

POWERS: Counter = Counter()  # what the PLAYER spent, and how often
ENDINGS: Counter = Counter()  # HOW a run ended — the number POINT_SHARE was tuned on
TURNS = {'player': 0}

# Per-card usage, to PRICE a Wu by how it is actually played rather than by eye. A battery is banked
# for points; a weapon is fielded in a showdown. `held` is the denominator — the card cannot be judged
# on turns it was never in hand to decide. `XS_CARD=<id>` focuses the report on one Wu; `XS_CARDS=1`
# prints the whole pool sorted battery-first. To measure a card's power SWING, pin it with
# `XS_SEED_COUNTERS=<id>` (forces it into hand every showdown) and read the win rate against a plain run.
HELD: Counter = Counter()     # times the card sat in the player's hand at a showdown opening
FIELDED: Counter = Counter()  # times the player chose to field it in a showdown
BANKED: Counter = Counter()   # times the player banked it for points

CATALOG = load_catalog()

# How often a full Mala Mala Jong set (five slots + the Heart) is ever holdable NATURALLY — no seeding,
# no set-hoarding policy. Tallied per run at each showdown opening; the assembly rate is the real
# balance gate on the exodia, so it is measured, not guessed.
NATURAL = {"runs": 0, "p_ever": 0, "b_ever": 0}

# Wuya's inherent initiative (power -6). Lives in the DB, not a module constant, so it is patched on
# the loaded catalog rather than imported — XS_WITCH_INIT=1 restores the +1 she shipped with before
# 2026-07-19. Every duelist built from this catalog shares the Power object, so one write is enough.
if os.environ.get('XS_WITCH_INIT'):
    for _c in CATALOG.opponents("boss"):
        if _c.power.id == -6:
            _c.power.initiative_bonus = int(os.environ['XS_WITCH_INIT'])


def competent_choices(state, rng, duel_ref):
    """The player, playing as well as the bot does — same functions, own side of the table.

    ``duel_ref`` is a one-slot list holding the Duel, so the card callback can read the contested
    stat and element off the board. Without it the player picks its card blind, which is not a
    player at all.
    """

    async def challenge(options):
        return bot.choose_challenge(
            state.player.character.stats, options, state.player.whole_hand,
            state.bot.character.stats, rng,
        )

    async def background(options):
        return bot.choose_background(
            state.player.character.stats, options,
            (state.player.whole_hand, state.bot.whole_hand),
            state.bot.character.stats, rng,
        )

    async def wager(options):
        return bot.choose_wager(options, state.player.whole_hand, state.bot.whole_hand)

    async def boost(options):
        duel = duel_ref[0]
        return bot.choose_boost(
            duel.duel.round, duel._ground(), options,
            duel._playable(state.player, is_player=True), is_player=True,
        )

    async def card(playable):
        duel = duel_ref[0]  # the player can see the board; so must the harness
        chosen = bot.choose_card(
            duel.duel.round, duel._ground(), playable, rng, is_player=True,
        )
        FIELDED[chosen.id] += 1  # priced: this Wu was played as a weapon, not banked
        return chosen

    async def counter(options):
        # A boosted Heart of Jong across the table: field the best answer. It is off-wager and free,
        # so a competent player always takes it — the harness models that with the same eval as a card.
        duel = duel_ref[0]
        return bot.choose_card(duel.duel.round, duel._ground(), options, rng, is_player=True)

    async def element(bg):
        return bg

    async def stat(options):
        """Where an Orb of Tornami or a Kaijin's Curse pours itself.

        The contested stat, which scores double — the obvious line. The callback is handed the three
        stats and nothing else, so it cannot play the alternative out the way `bot.choose_stat` does;
        a player who pours into a side stat on purpose is doing something this harness cannot model.
        """
        duel = duel_ref[0]
        challenge = duel.duel.challenge
        return challenge if challenge in options else options[0]

    return DuelChoices(challenge, background, wager, boost, card, element, stat, counter=counter)


def player_temple_action(state, settings, rng, difficulty):
    """The player's ONE action a turn, by exactly the policy the opponent plays (`turn._bot_acts`).

    A turn buys one action — spend a Wu's power, fly the Early Bird, draw, or bank. The ORDER matters
    and it is the opponent's, not an invention: a power that wins the next showdown outranks two points
    in the temple.

    **This is what made every past player win rate a floor.** The simulated player used to bank and draw
    and nothing else, so the whole in-duel half of the card pool — the pours, the negations, the
    revealers — was never *played* from the player's seat, only ever suffered from the opponent's. Now
    both duelists spend powers by the same rules, and the two sides differ only in their stats.
    """
    # A waiting payout is free in the game (the temple's picker costs no action) — cash it by the
    # bot's own policy, the lowest stat with room, before choosing the turn's action.
    if payout_ready(state.player, settings):
        raise_stat(state.player, pick_stat(state.player, settings))

    # Mala Mala Jong: assemble the moment the set is in hand, then take no temple action while locked —
    # the construct races the game to its close on its 6/6/6. Mirrors turn._construct_jong for the bot.
    if bot.is_jong(state.player):
        return
    from xiaolin_showdown.logic.flow.actions import can_construct, construct_jong
    if can_construct(state, player_actions(state, settings), is_player=True):
        construct_jong(state, is_player=True)
        return

    play = choose_temple_power(state, settings, is_player=True)
    if play is not None:
        POWERS[mechanic_of(play.card.power)] += 1
        use_power(
            state,
            play.card,
            settings,
            is_player=True,
            priority=play.priority,
            target=play.target,
            to_deck=play.to_deck,
            rng=rng,
        )
        return

    bird = choose_early_bird(state, settings, is_player=True)
    if bird is not None:
        FLIGHTS["player"] += 1
        early_bird(state, bird, is_player=True)
        return

    # Mirror `turn._bot_acts`: the last stretch of a nearly-full bar outranks drawing or banking.
    if (
        can_train(state.player, settings)
        and not state.player.just_trained
        and settings.train_length_player - state.player.training <= 4
    ):
        if train(state, settings):
            raise_stat(state.player, pick_stat(state.player, settings))
        return

    if len(state.player.hand) < settings.max_wager and state.player.deck:
        draw(state)
        return
    if len(state.player.hand) > DUEL_FLOOR:
        banked = pick_deposit(state.player.hand, difficulty, settings.wear_limit)
        if banked is not None:
            BANKED[banked.id] += 1  # priced: this Wu was cashed as a battery, not fielded
            deposit(state, banked, rng=rng)


async def play(seed, difficulty):
    rng = Rng(seed)
    import os
    # Mirror the real game's boot-time refresh (`Game.refresh_settings=refreshed_for_pool`) — without
    # it, `options={}` leaves `max_deck_size`/`point_limit` at their pool-wide field defaults (83/69),
    # which `_player_set_their_own_deal` reads as "customised" and silently skips the weighted-pile
    # deal for every tier, not just boss. A harness bug, not a game one — a real player's settings are
    # always refreshed before `new_game` ever sees them.
    settings = XiaolinSettings.from_settings(refreshed_for_pool(Settings(difficulty=difficulty, options={})))
    if os.environ.get("XS_POINTS"):
        settings = XiaolinSettings(**{**settings.__dict__, "point_limit": int(os.environ["XS_POINTS"])})
    if os.environ.get("XS_CHOSEN_BG"):  # turn the default random arena OFF — the non-challenger picks
        settings = XiaolinSettings(**{**settings.__dict__, "random_background": 0})
    # Set the gap out of reach and the Early Bird cannot be flown by anyone — the clean A/B for
    # "what does this rule do", with every other knob and every seed held fixed.
    if os.environ.get("XS_GAP"):
        settings = XiaolinSettings(
            **{**settings.__dict__, "early_bird_gap": int(os.environ["XS_GAP"])}
        )
    if os.environ.get("XS_MERCY"):
        settings = XiaolinSettings(
            **{**settings.__dict__, "empty_draw_limit": int(os.environ["XS_MERCY"])}
        )
    if os.environ.get("XS_THRESHOLD"):
        settings = XiaolinSettings(
            **{**settings.__dict__, "prize_threshold": int(os.environ["XS_THRESHOLD"])}
        )
    # The hard tier is a tougher OPPONENT ROSTER, not just a keener deposit rule. Left out, both
    # tiers fought the easy roster and 'hard' measured as the easier game.
    # XS_BOSS pins WHICH boss the boss tier fights (substring of the name) — with two on the
    # roster, a random pick would measure a blend and attribute it to nobody.
    _boss_pick = None
    if os.environ.get("XS_BOSS") and roster_of(difficulty) == "boss":
        _wanted = os.environ["XS_BOSS"].lower()
        _boss_pick = next(c for c in CATALOG.opponents("boss") if _wanted in c.name.lower())
    state = new_game(CATALOG, rng, CATALOG.character(1), settings=settings,
                     roster=roster_of(difficulty), opponent=_boss_pick)

    # Ceiling test: hand the player a guaranteed Celestial Dial (card 45) every showdown, to isolate
    # "does the reverse counter the boss" from "does the player draw it". Re-seeded each refill below.
    from copy import deepcopy as _dc  # noqa: E402
    # Ceiling test: keep the given counter card ids in the player's hand every turn (see the loop),
    # to isolate "does the counter work" from "does the player draw it".
    _seed_ids = [int(x) for x in os.environ.get("XS_SEED_COUNTERS", "").split(",") if x]

    # Duel-side asymmetry test: the player's base stats get +N in a boss run, to contest the showdowns.
    _pstat = int(os.environ.get("XS_PLAYER_STATS", 0))
    if _pstat:
        for _s in state.player.character.stats:
            state.player.character.stats[_s] += _pstat

    # The opponent's OPENING turn. The game gives it one at character select — every later turn of
    # theirs runs as a showdown ends, and the first has no showdown in front of it. The harness used to
    # skip it, so the opponent played a run one action short of the game's, every run, forever.
    if not os.environ.get("XS_NO_OPENING_TURN"):
        bot_turn(state, settings, rng=rng, difficulty=difficulty)
        state.bot_turn_done = True
        refill_hands(state, settings, rng=rng)

    showdowns = 0
    NATURAL["runs"] += 1
    nat_p = nat_b = False  # did a full set ever come holdable, naturally, this run
    wear_p = wear_b = 0  # Wu the wear rule vaulted, per side
    hands = []          # (player playable, bot playable) at each showdown opening
    caps = []           # the largest best-of-N both sides could field
    wagers = []         # what was actually staked
    claimed = []        # the route the prize was claimed by, or None when the Wu was lost
    challenges = []     # (what was called, was a tournament even offered?)

    while not state.has_ended and showdowns < 60:
        p, b = len(state.player.hand), len(state.bot.hand)
        hands.append((p, b))
        caps.append(min(p, b, 3))
        for _held in state.player.hand:  # the denominator: it can only be judged on turns it was in hand
            HELD[_held.id] += 1

        # Natural assembly: did a full set ever come holdable this run, without seeding? `can_construct`
        # reads the hand gate; `is_jong` catches a side that already assembled (so the count survives it).
        if jong.can_construct(state.player) or bot.is_jong(state.player):
            nat_p = True
        if jong.can_construct(state.bot) or bot.is_jong(state.bot):
            nat_b = True

        TURNS['player'] += 1
        # The player's budget is the GAME's own rule now (3 vs a boss — settings.player_actions);
        # XS_PLAYER_ACTIONS still overrides it for sweeps. Resetting the counter each loop lets each
        # action through the budget the game logic enforces.
        from xiaolin_showdown.logic.config.settings import player_actions as _budget
        for _ in range(int(os.environ.get("XS_PLAYER_ACTIONS", 0)) or _budget(state, settings)):
            state.actions_taken = 0
            player_temple_action(state, settings, rng, difficulty)  # the player's action a turn
            if state.player.points >= settings.point_limit:
                state.has_ended = True
                break
        if state.player.points >= settings.point_limit:
            state.has_ended = True
        # The Early Bird can take the LAST Wu off the pile, which ends the run there and then — the
        # temple screen greys the duel out for exactly this. Without the check the harness opened a
        # showdown against an empty pile and popped from an empty list.
        if state.has_ended:
            break

        # read BEFORE the duel runs: a tournament stakes three Wu, so a hand that could field one is
        # always short of three by the time it ends. Reading it after counted zero tournaments, ever.
        could_tournament = min(len(state.player.hand), len(state.bot.hand)) >= 3

        if not bot.is_jong(state.player):  # a locked construct's hand only shrinks — never top it up
            for _cid in _seed_ids:  # top up the seeded counters so the player holds them every showdown
                if not any(c.id == _cid for c in state.player.hand):
                    state.player.hand.append(_dc(CATALOG.card(_cid)))

        duel_ref: list = []
        duel = Duel(state, rng, competent_choices(state, rng, duel_ref), settings)
        duel_ref.append(duel)
        if os.environ.get("XS_FORCE_REVERSE"):  # ceiling: the elemental bonus reversed every showdown
            duel.duel.elemental_bonus_reversed = True
        stage, guard = -1, 0
        while stage != 0 and guard < 12:
            stage = await duel.advance()
            guard += 1
        showdowns += 1
        wear_p += sum(1 for _, was_p, _ in duel.duel.worn_out if was_p)
        wear_b += sum(1 for _, was_p, _ in duel.duel.worn_out if not was_p)
        challenges.append((duel.duel.challenge, could_tournament))
        # A tournament never asks for a wager (three battles of one Wu), so `duel.wager` sits at its
        # default. Counting it as a wager reported every tournament as a timid best-of-1.
        if duel.duel.challenge != "tournament":
            wagers.append(duel.duel.wager)
        if duel.duel.stakes is not None:  # the pile put a Wu up, so a prize route could fire
            claimed.append(str(duel.duel.prize_route) if duel.duel.card_won else None)
        if state.has_ended:
            break
        refill_hands(state, settings, rng=rng)
        FLIGHTS['leads'].append(initiative_lead(state, is_player=True))
        if not state.has_ended:
            moves = bot_turn(state, settings, rng=rng, difficulty=difficulty)
            # Count the ACTION, not the prose. This used to grep the bot's own sentence for "stolen
            # from under your nose", and a reworded line silently zeroed the counter for a whole
            # sweep. A move now says what it was (`BotMove.action`), so there is nothing to grep.
            FLIGHTS['bot'] += sum(1 for move in moves if move.action == EARLY_BIRD)
            FLIGHTS.setdefault('bot_powers', [0])[0] += sum(
                1 for move in moves if move.action in ("Power", "Witchcraft")
            )
        refill_hands(state, settings, rng=rng)

    if nat_p:
        NATURAL["p_ever"] += 1
    if nat_b:
        NATURAL["b_ever"] += 1

    if state.player.points >= settings.point_limit or state.bot.points >= settings.point_limit:
        ENDINGS[str(difficulty) + ":target"] += 1
    elif not state.card_deck:
        ENDINGS[str(difficulty) + ":empty pile"] += 1
    else:
        ENDINGS[str(difficulty) + ":ran long"] += 1  # hit the showdown guard — should be ~never

    # leftover Wu are cashed at the end, so the final score includes the hand
    player_final = state.player.points + sum(c.points for c in state.player.whole_hand)
    bot_final = state.bot.points + sum(c.points for c in state.bot.whole_hand)
    # Training audit: stat points above the PRINTED line are payouts actually taken this run.
    _printed = lambda ch: sum(CATALOG.character(ch.id).stats.values())  # noqa: E731
    return {
        "seed": seed,
        "difficulty": str(difficulty),
        "player_raises": sum(state.player.character.stats.values()) - _printed(state.player.character),
        "bot_raises": sum(state.bot.character.stats.values()) - _printed(state.bot.character),
        "player_bar": state.player.training,
        "wear_p": wear_p,
        "wear_b": wear_b,
        "showdowns": showdowns,
        "player_points": player_final,
        "bot_points": bot_final,
        "player_won": player_final > bot_final,
        "hands": hands,
        "caps": caps,
        "wagers": wagers,
        "claimed": claimed,
        "challenges": challenges,
    }


async def main():
    rows = []
    for difficulty in (Difficulty.EASY, Difficulty.HARD, Difficulty.BOSS):
        for seed in range(1, RUNS + 1):
            rows.append(await play(seed, difficulty))

    print(f"{RUNS} runs per difficulty, competent player on both sides\n")
    for tag in ("easy", "hard", "boss"):
        r = [x for x in rows if x["difficulty"] == tag]
        wins = sum(x["player_won"] for x in r)
        print(f"  {tag:5}  player wins {wins:3}/{len(r)}  ({wins / len(r) * 100:4.1f}%)   "
              f"avg pts {mean(x['player_points'] for x in r):5.1f} v {mean(x['bot_points'] for x in r):5.1f}   "
              f"showdowns {mean(x['showdowns'] for x in r):4.1f}   "
              f"raises {mean(x['player_raises'] for x in r):.2f} v {mean(x['bot_raises'] for x in r):.2f}   "
              f"end bar {mean(x['player_bar'] for x in r):.1f}/10   "
              f"wear vaults {mean(x['wear_p'] for x in r):.2f} v {mean(x['wear_b'] for x in r):.2f}")

    _nr = NATURAL["runs"] or 1
    print(f"\n  Mala Mala Jong natural assembly (no seeding): a full set was ever holdable in "
          f"{NATURAL['p_ever']}/{NATURAL['runs']} player runs ({NATURAL['p_ever'] / _nr * 100:.1f}%), "
          f"{NATURAL['b_ever']}/{NATURAL['runs']} bot runs ({NATURAL['b_ever'] / _nr * 100:.1f}%)")

    every_hand = [h for x in rows for h in x["hands"]]
    every_cap = [c for x in rows for c in x["caps"]]
    print(f"\n  hand size at a showdown:  player {mean(h[0] for h in every_hand):.1f}   "
          f"bot {mean(h[1] for h in every_hand):.1f}")
    every_wager = [w for x in rows for w in x["wagers"]]
    print("  wagers actually called (STAT CHALLENGES only — a tournament asks for none):")
    for n in (1, 2, 3):
        share = sum(1 for w in every_wager if w == n) / len(every_wager) * 100
        print(f"    best of {n}: {share:5.1f}%")
    print("  largest wager both sides could field:")
    for n in (0, 1, 2, 3):
        share = sum(1 for c in every_cap if c == n) / len(every_cap) * 100
        print(f"    best of {n}: {share:5.1f}%")

    called = [c for x in rows for c in x["challenges"]]
    offered = [c for c in called if c[1]]
    if offered:
        took = sum(1 for c, _ in offered if c == "tournament")
        print(f"\n  a tournament was CALLABLE in {len(offered)}/{len(called)} showdowns "
              f"({len(offered) / len(called) * 100:4.1f}%) — and called {took} times "
              f"({took / len(offered) * 100:4.1f}% of the time it could be)")

    print("\n  how the run ended:")
    for tag in ("easy", "hard", "boss"):
        # NOT `rows` — that name holds the runs, and every report below this reads it. Shadowing it
        # here killed the prize-threshold report with a TypeError the moment anything looked at it.
        endings = {k.split(":")[1]: v for k, v in ENDINGS.items() if k.startswith(tag)}
        total = sum(endings.values()) or 1
        parts = "   ".join(
            f"{why} {count / total * 100:4.1f}%" for why, count in sorted(endings.items())
        )
        print(f"    {tag:5} {parts}")

    spent = sum(POWERS.values())
    print(f"\n  the player spent a Wu's power on {spent}/{TURNS['player']} of its temple turns "
          f"({spent / max(1, TURNS['player']) * 100:4.1f}%)")
    for mechanic, count in POWERS.most_common():
        print(f"    {str(mechanic):16} {count:5}")

    leads = FLIGHTS["leads"]
    reached = sum(1 for lead in leads if lead >= actions.EARLY_BIRD_GAP)
    print(f"\n  the opponent fired a temple power {FLIGHTS.get('bot_powers', [0])[0]}x across all runs")
    print(f"  the Early Bird: flown {FLIGHTS['player']}x by the player, {FLIGHTS['bot']}x by the "
          f"opponent — the gap was reachable in {reached}/{len(leads)} player turns "
          f"({reached / max(1, len(leads)) * 100:4.1f}%)")

    every_claim = [c for x in rows for c in x["claimed"]]
    if every_claim:
        won = sum(1 for c in every_claim if c is not None)
        bar = os.environ.get("XS_THRESHOLD") or XiaolinSettings().prize_threshold
        print(f"\n  prize_threshold {bar} — the prize was claimed in "
              f"{won}/{len(every_claim)} showdowns "
              f"({won / len(every_claim) * 100:4.1f}%); the rest were lost")
        for route in sorted({c for c in every_claim if c}):
            share = sum(1 for c in every_claim if c == route) / len(every_claim) * 100
            print(f"    {route:28} {share:5.1f}%")

    # Card pricing table (on demand): how each Wu was actually PLAYED — banked as a battery or fielded as
    # a weapon — so a point cost can follow behaviour instead of a guess. `bank%` is of the times it was
    # played at all; `field/held` is how often it went to a fight when it could have. Sorted battery-first.
    if os.environ.get("XS_CARD") or os.environ.get("XS_CARDS"):
        focus = os.environ.get("XS_CARD")
        ids = [int(focus)] if focus else sorted(
            set(HELD) | set(FIELDED) | set(BANKED),
            key=lambda i: -(BANKED[i] / max(1, FIELDED[i] + BANKED[i])),
        )
        print("\n  how each Wu was played (a battery banks, a weapon fields):")
        for i in ids:
            played = FIELDED[i] + BANKED[i]
            bankshare = BANKED[i] / played * 100 if played else 0
            fieldrate = FIELDED[i] / HELD[i] * 100 if HELD[i] else 0
            print(f"    {CATALOG.card(i).name:22} pts {CATALOG.card(i).points}   held {HELD[i]:5}   "
                  f"fielded {FIELDED[i]:5} ({fieldrate:3.0f}% of held)   banked {BANKED[i]:5}   "
                  f"bank {bankshare:3.0f}% of plays")

    with open("C:/tmp/oldcat/balance.json", "w") as fh:
        json.dump([{k: v for k, v in r.items() if k not in ("hands", "caps", "wagers")} for r in rows], fh)


asyncio.run(main())
