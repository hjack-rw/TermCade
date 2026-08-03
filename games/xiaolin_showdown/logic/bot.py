"""The opponent's decisions — pure, RNG-injected.

Two kinds, and they are not equally good. What to *field* is searched: every candidate Wu is played
into a copy of the real battle and weighed by :func:`~.battle.score_battle`, the same scorer the duel
itself uses, so the opponent and the referee can never disagree about what a card is worth. What to
*call* — the challenge, the background, the wager — is still heuristic, judged on hand strength
rather than played out.

Every one of them is blind to what the other duelist is committing to this exchange. The duel hands
over a frozen copy of the ground for exactly that reason: Gong Yi Tanpai is a simultaneous reveal,
and the order this code happens to run in must never leak.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import replace

from termcade.core.rng import Rng

from .battle import Ground, Round, Side, score_battle
from .constants import OPPOSITES, TOURNAMENT
from . import jack
from .mechanics.powers import Mechanic, is_uncontrolled, mechanic_of, names_a_stat
from .mechanics.resolve import as_boost, resolve_played_power
from .models import Card, Player
from .turn import duel_value

# Chase Young activates Beast Form only when a contested stat is close — his lead on it is under
# `duel.BEAST_BOOST`, so the boost could decide the battle. Ahead by more he stays an ordinary
# duelist: his Wu score, and a win GIFTS the prize to the duelist he beat. Swept from the harness
# (XS_BEAST_MARGIN).
#
# Since the beast KEEPS its prize (see the duel's `_award_prize`), beasting more makes him STRONGER,
# monotonically: 0 (never) 5.5% player win, 2 -> 3.2%, 4 -> 2.5%, always -> 2.0% (n=600). Sweeps
# taken before the prize flip read this slope the other way round.
#
# Three, paired with a BEAST_BOOST of 1: the pair reads 7.1% player win and the beast fires on 61%
# of his showdowns, so the mode is a real choice rather than a rule. At boost 2 the curve was crushed
# flat and every route to this win rate meant a Chase who barely beasts at all.
BEAST_MARGIN = 3


def choose_beast_form(chase: Player, opponent: Player, stats: Sequence[str]) -> str | None:
    """Chase's per-showdown call: which contested stat to spend Beast Form on, or ``None``.

    Beast Form is `duel.BEAST_BOOST` on ONE stat, once a fight, and it deadens his Wu — they are
    wagered, never wielded. What it does NOT cost him is the prize: the beast KEEPS what it wins,
    and it is the ordinary Wu-play win that gifts the prize away (see the duel's `_award_prize`).
    That is why beasting more makes him stronger, and why the margin below is the whole choice.

    So he spends it where a battle is close: the tightest contested stat, where his base lead over
    the opponent's reach is under the margin. Ahead by more on all of them, he fields his Wu like
    anyone else — and gifts the prize if he wins.

    ``stats`` is the contested set — one stat for a challenge, all three for a tournament (he may
    still boost only one).
    """
    def lead(stat: str) -> int:
        reach = opponent.character.stats[stat] + max(
            (card.stats[stat] or 0 for card in opponent.hand), default=0
        )
        return chase.character.stats[stat] - reach

    tightest = min(stats, key=lead)
    return tightest if lead(tightest) < BEAST_MARGIN else None


def choose_jack_bot(opponent: Side) -> bool:
    """Jack's per-boost call: deploy Jack-Bot to curse the opponent (``True``), or hold it back for
    a normal Wu self-buff instead (``False``) — Jack-Bot itself never buffs, only curses.

    v1, swept later like every other boss knob: deploy it unless the opponent already can't be
    cursed this battle (a Reversing Mirror is up), where a self-buff never can be blocked. Excluded
    from the generic ``choose_boost`` comparison (see there) because that machinery only knows how
    to weigh a boost against the caster's *own* reach — never one that lands on the opponent instead.
    """
    return not opponent.defence_negated


ATTACK_MIN_CHANCE = 5  # a floor: it never fully vanishes, only fades — still "unpredictable by design"
ATTACK_MAX_CHANCE = 90  # a ceiling: even desperate, there is always some chance he stays himself

# Attack! always transfers the full prize outright, no partial-credit ladder (`PrizeRoute.BRAWL_WON`)
# — so its VALUE isn't its own per-showdown win rate in isolation, it's that rate against what it
# replaces. Once Chamelon-Bot was redesigned (below) to actually hold its own when the player leads
# (~30% Jack win, up from the old ~15-19%), Attack! stopped being an improvement over either
# alternative and became a pure drag: more full-prize losses with no offsetting upside. Swept 0-70
# (n=300 each) post-redesign — the aggregate got monotonically WORSE as Attack!'s share grew in
# EITHER branch. So both are now near-floor: rare enough to keep him "unpredictable by design"
# without being the number that decides the run — see BOSSES.md.
ATTACK_CHANCE_WHEN_LEADING = 2  # percent — Jack leads, "himself"/AI Jack are already strong

ATTACK_CHANCE_WHEN_TRAILING = 5  # percent at momentum 0 — Chamelon-Bot now covers this spot instead
# `jack_attack_momentum` (XiaolinState) still shifts this with the run's recent record — losing a
# showdown reaches for Attack! harder, winning one leaves it alone — clamped to +-ATTACK_MOMENTUM_CAP,
# a fresh run starting at 0. Kept even though the redesign made Attack! a minor lever: momentum being
# net-neutral-to-positive here is not a reason to strip a mechanic that costs nothing to keep.
ATTACK_MOMENTUM_STEP = 10  # percentage points shifted per showdown won/lost, applied only here
ATTACK_MOMENTUM_CAP = 30  # how far a streak can push the trailing chance off its base, either way

# A losing showdown fighting as HIMSELF (never a stand-in, never Attack! — those already have their
# own economics) costs him twice: his own wager and, at `prize_threshold`'s usual rate, the prize
# too. Fleeing trades a coward's escape for both: no route can claim the prize (it goes to lost,
# never to the winner — strictly better than the ~61% of losses that hand it over outright today),
# and his wager stays his. No downside on any single use, so it is capped instead of tuned — a scarce
# resource he burns on his worst run of showdowns, not a standing "never actually lose" rule.
JACK_FLEE_CAP = 3  # per run — v1, swept later like every other boss knob


def choose_to_flee(flees_used: int) -> bool:
    """Whether Jack concedes a showdown he has already lost, rather than pay the normal cost."""
    return flees_used < JACK_FLEE_CAP


# Chamelon-Bot used to be gated by a margin on the SUM of all three stats ("only mirror when it
# looks worth it") — swept 0/1/2/3/4 (n=300 each) and it lost to fighting as himself at EVERY value,
# because a full mirror traded his real intellect edge on the two UNCONTESTED stats for a coin-flip
# on the one that mattered, and the sum told it nothing about the single stat actually in play.
# Redesigned twice: first to raise his OWN contested stat to the opponent's and no further (never
# touching the other two), which needed no margin since there was no longer a downside to deny — then
# again to make that denial a BOOST (see `duel.Duel._chamelon_boost_card`), competing with a real Wu
# for the one boost his fielded Wu gets — fed straight into `choose_boost`'s own reach-comparison
# alongside Shimo Staff, the Heart, or anything else in hand, rather than preferred by default (it
# targets his OWN side, unlike Jack-Bot's curse, so the same machinery can weigh it fairly). Still
# fires unconditionally whenever the player leads — what changed is whether he SPENDS it that cycle.
def _attack_chance(player_has_priority: bool, momentum: int) -> int:
    """Attack!'s own percentage this showdown. Jack leading is always low, whatever his form —
    Attack! only hurts him there. Player leading is his base rate plus momentum (his recent
    showdown record this run), clamped to the floor and ceiling."""
    if not player_has_priority:
        return ATTACK_CHANCE_WHEN_LEADING
    return max(ATTACK_MIN_CHANCE, min(ATTACK_MAX_CHANCE, ATTACK_CHANCE_WHEN_TRAILING + momentum))


def choose_jack_mode(
    player_has_priority: bool,
    can_swap: bool,
    momentum: int,
    rng: Rng,
) -> str | None:
    """Jack's identity swap, decided once at commitment: Attack!, a stand-in, or himself.

    v1, swept later like every other boss knob. Attack! rolls first, a priority-aware percentage
    (`_attack_chance`) — high when it would replace Jack's weakest spot (fighting as himself while
    the player leads), and higher still there the more he has been losing this run (`momentum`);
    low when it would replace his strongest (himself/AI Jack while he leads), regardless of
    momentum. It neither reads nor writes `can_swap`, so it never disrupts the pattern underneath it.

    Missing that roll, priority decides which stand-in is even on the table — the two never compete:
    Chamelon-Bot when the player is about to name the challenge (unconditional — see the redesign
    note above); AI Jack when HE leads instead (he already picks intellect there, so a steal is pure
    upside), gated by `can_swap` alone — the "cannot spam a stand-in" rule is his, not Chamelon-Bot's.
    """
    if rng.randint(1, 100) <= _attack_chance(player_has_priority, momentum):
        return jack.ATTACK_NAME
    if player_has_priority:
        return jack.CHAMELON_NAME
    return jack.AI_JACK_NAME if can_swap else None


def steal_target(hand: Sequence[Card], deck: Sequence[Card], rng: Rng) -> Card | None:
    """AI Jack's steal: the strongest Wu in the opponent's hand — fully known, so judged like any
    other bot decision. An empty hand falls back to a random deck card: nothing is known about it
    (see the deferred reveal-memory note in ``docs/PLAN.md``), so there is nothing to rank it by."""
    if hand:
        return max(hand, key=duel_value)
    if deck:
        return rng.choice(list(deck))
    return None


def choose_challenge(
    bot_stats: Mapping[str, int],
    challenges: Sequence[str],
    bot_hand: Sequence[Card],
    opponent_stats: Mapping[str, int],
    rng: Rng,
) -> str:
    """Call the stat the bot is strongest in — or a tournament, when it is strong in most of them.

    The two challenges reward opposite hands, and this is the decision that says which one the bot
    thinks it holds. A tournament is three battles on three stats, so it goes to the broad hand: call
    it only when the bot leads on a *majority* of the stats, because leading on one and losing two
    hands the opponent the match. A narrow hand does the reverse — it names its one good stat and
    pours everything into that single battle.
    """
    edges = {stat: _edge(stat, bot_stats, bot_hand, opponent_stats) for stat in bot_stats}
    if TOURNAMENT in challenges:
        ahead = sum(1 for edge in edges.values() if edge > 0)
        if ahead * 2 > len(edges):  # ahead on most of them — take all three
            return TOURNAMENT

    stats = [stat for stat in edges if stat in challenges]
    if not stats:
        return rng.choice(list(challenges))
    return max(stats, key=lambda stat: edges[stat])


def _edge(
    stat: str,
    bot_stats: Mapping[str, int],
    bot_hand: Sequence[Card],
    opponent_stats: Mapping[str, int],
) -> int:
    """How far ahead the bot is on ``stat`` once it plays its best Wu for it."""
    best_card = max((card.stats[stat] or 0 for card in bot_hand), default=0)
    return bot_stats[stat] + best_card - opponent_stats[stat]


def choose_background(
    bot_stats: Mapping[str, int],
    backgrounds: Sequence[str],
    hands: tuple[Sequence[Card], Sequence[Card]],
    opponent_stats: Mapping[str, int],
    rng: Rng,
) -> str:
    """Pick the element that best boosts the bot; else counter the player's dominant element."""
    bot_hand, player_hand = hands
    best_value = max(bot_stats.values())
    element: str | None = None
    for card in bot_hand:
        for stat in bot_stats:
            if card.element in backgrounds:
                value = (card.stats[stat] or 0) + bot_stats[stat] - opponent_stats[stat]
                if value > best_value:
                    best_value, element = value, card.element
    if element is not None:
        return element
    return _counter_element(player_hand, backgrounds, rng)


def _counter_element(
    player_hand: Sequence[Card], backgrounds: Sequence[str], rng: Rng
) -> str:
    """No boost available — counter the player: against a wudai lead card prefer metal or its
    opposite, otherwise counter the player's most common element.

    An EMPTY hand has no element to counter — a hand can run dry between refills now that wear
    vaults Wu mid-showdown and the Lantern can take everything at once. Nothing to read, so roll.
    """
    if not player_hand:
        return rng.choice(list(backgrounds))
    if player_hand[0].type == "wudai":
        counters = ["metal", OPPOSITES.get(player_hand[0].element, "metal")]
    else:
        dominant = _most_common_element(player_hand)
        if dominant == "metal":
            non_metal = [b for b in backgrounds if b != "metal"]
            return rng.choice(non_metal) if non_metal else rng.choice(list(backgrounds))
        counters = ["metal", OPPOSITES[dominant]]

    for background in counters:
        if background in backgrounds:
            return background
    return rng.choice(list(backgrounds))


def choose_card(
    battle: Round,
    ground: Ground,
    playable: Sequence[Card],
    rng: Rng,
    *,
    is_player: bool = False,
) -> Card:
    """Field the Wu that leaves the battle in the best shape.

    ``battle`` is the ground as it stood before *anyone* committed this exchange — Gong Yi Tanpai is
    a simultaneous reveal, and the duel hands over a frozen copy precisely so this cannot read the Wu
    the other duelist is committing to. Each candidate is played into a copy of it and scored by the
    rule the duel itself uses, and the lowest score wins: a battle's score is signed from the player's
    side, so the player drives it up and the opponent drives it down.

    Ties are broken by hitting harder, never by holding back. Only the *loser* forfeits what they
    staked, so a Wu spent on a battle you win costs nothing — and the prize is claimed only when the
    contested stat beats ``prize_threshold``, which a duelist who wins by the minimum never does.
    """
    if not playable:
        raise ValueError("nothing to field")

    # The Sapphire Dragon loses the showdown for whoever fields it — hold it back unless it is the only
    # Wu left to answer with. Its instant level is a temple play; the bot never throws a duel on it.
    safe = [card for card in playable if not is_uncontrolled(card.power)]
    if safe:
        playable = safe

    # A Treasurebox of the Blind Swordsman wins the showdown outright — field it over anything scored
    # on stats. The bot keeps it for exactly this: pick_deposit never banks it away.
    for card in playable:
        if mechanic_of(card.power) is Mechanic.WISH:
            return card

    best: Card | None = None
    best_key: tuple[int, int] | None = None
    for card in playable:
        key = _after(battle, ground, card, is_player=is_player)
        if best_key is None or key < best_key:
            best, best_key = card, key
    return best if best is not None else rng.choice(list(playable))


def choose_boost(
    battle: Round,
    ground: Ground,
    options: Sequence[Card],
    playable: Sequence[Card],
    *,
    is_player: bool = False,
) -> Card | None:
    """Lay a boost ahead of the Wu about to be fielded, or decline.

    A boost is only worth playing if it improves the best Wu the bot could then field, so each option
    is judged by what it makes reachable — and declining is judged the same way. A boost taken out of
    hand costs the Wu it would have been, which is why it is dropped from what remains playable.

    The Heart of Jong is never boosted here: its summon hands the far side a free off-wager Wu that
    answers it, so the extra body nets out — the naive reach-score would over-count it, blind to that
    cost. The bot fields the Heart as a plain 2/2/2 instead. (A construct's own 1/1/1 Heart boost has
    no such cost, but the bot ~never assembles, so the simple exclusion is worth more than the nuance.)

    Jack-Bot is never boosted here either: it curses the *opponent*, and "what it makes reachable"
    only ever measures the caster's own side. See `choose_jack_bot`, decided separately before this
    is even called.
    """
    options = [o for o in options if mechanic_of(o.power) not in (Mechanic.ANIMATE, Mechanic.BOT)]
    if not options:
        return None

    best: Card | None = None
    best_score = _reachable(battle, ground, None, playable, is_player=is_player)
    for boost in options:
        score = _reachable(battle, ground, boost, playable, is_player=is_player)
        if score < best_score:
            best, best_score = boost, score
    return best


def choose_stat(battle: Round, ground: Ground, card: Card, *, is_player: bool = False) -> str:
    """Which stat the Orb or the Curse pours itself into.

    Played out rather than guessed at: every stat is fielded in a trial battle and the one that
    leaves the board best is taken. Usually that is the contested stat — it scores double — but not
    always, and the bot finds the exception for the same reason a player would.
    """
    return min(
        _stat_options(ground, card),
        key=lambda stat: _after(battle, ground, card, is_player=is_player, stat=stat),
    )


def _stat_options(ground: Ground, card: Card) -> list[str]:
    """The stats a Wu may be poured into — the ground's, or the card's own before one is set."""
    return list(ground.stats) or list(card.stats)


def _after(
    battle: Round, ground: Ground, card: Card, *, is_player: bool, stat: str | None = None
) -> tuple[int, int]:
    """How the battle stands once ``card`` is fielded. Lower is better *for the duelist fielding it*.

    ``(score, -blow)``: the score first, because winning the battle is what wins the showdown, and
    the size of the blow only to separate fields that win by the same margin. A battle's score is
    signed from the player's side, so the player maximises it and the bot minimises it.

    A Wu that names a stat is worth what its *best* stat is worth — so weighing whether to play it at
    all (``choose_card``) asks this without a stat, and gets the best line it could take.
    """
    if stat is None and names_a_stat(card.power):
        return min(
            _after(battle, ground, card, is_player=is_player, stat=option)
            for option in _stat_options(ground, card)
        )

    trial = deepcopy(battle)
    effect = resolve_played_power(
        trial, card, is_player=is_player, element=ground.background, stat=stat
    )
    terms = replace(
        ground,
        bonus_cancelled=ground.bonus_cancelled or effect == "cancel",
        bonus_reversed=ground.bonus_reversed or effect == "reverse",
    )
    score_battle(trial, terms)
    sign = -1 if is_player else 1
    return sign * trial.score, -_blow(trial, terms, is_player=is_player)


def _blow(battle: Round, ground: Ground, *, is_player: bool) -> int:
    """A duelist's end value on the contested stat — what the prize Wu is measured against."""
    mine, _theirs = battle.sides(is_player)
    if battle.stat not in ground.stats or not mine.result:
        return 0
    return mine.result[list(ground.stats).index(battle.stat)]


def _reachable(
    battle: Round,
    ground: Ground,
    boost: Card | None,
    playable: Sequence[Card],
    *,
    is_player: bool,
) -> tuple[int, int]:
    """The best this duelist could reach from here, having laid ``boost`` (or nothing) first."""
    trial = deepcopy(battle)
    mine, _theirs = trial.sides(is_player)
    remaining = list(playable)
    if boost is not None:
        # Resolve the boost the way the duel will (a Morpher nets 1/1/1 in tune — see `as_boost`),
        # or the bot prices a wudai Morpher at its unresolved 0/0/0 and never plays it.
        mine.queue.append(as_boost(boost, ground.background, trial.stat))
        remaining = [card for card in remaining if card is not boost]

    if not remaining:
        score_battle(trial, ground)
        sign = -1 if is_player else 1
        return sign * trial.score, -_blow(trial, ground, is_player=is_player)
    return min(_after(trial, ground, card, is_player=is_player) for card in remaining)


def _most_common_element(hand: Sequence[Card]) -> str:
    counts: dict[str, int] = {}
    for card in hand:
        counts[card.element] = counts.get(card.element, 0) + 1
    return max(counts, key=lambda e: counts[e])


def choose_wager(options: Sequence[int], own_hand: Sequence[Card], opponent_hand: Sequence[Card]) -> int:
    """How wide to make the battle — the answer to a stat challenge you did not call.

    Width IS the bet: every wagered Wu lands at once and the loser forfeits all of them. So price it by
    the whole field's margin, not rung by rung — take the widest width you lead at, else the narrowest.
    A deep bench widens; one monster and two trinkets narrows.
    """
    if not options:
        return 1
    mine = sorted((duel_value(card) for card in own_hand), reverse=True)
    theirs = sorted((duel_value(card) for card in opponent_hand), reverse=True)

    def margin(width: int) -> int:
        """What the whole field would carry at this width, theirs subtracted from mine."""
        return sum(mine[:width]) - sum(theirs[:width])

    # Take the WIDEST field you are still ahead in; if you are behind in all of them, take the
    # narrowest bet on offer.
    #
    # That is the expected-swing rule: the swing is `w x (2P - 1)`, and any sane reading of a margin
    # into a chance is monotone — so the best width turns on the *sign* of the margin, not its scale.
    ahead = [width for width in options if margin(width) > 0]
    return max(ahead) if ahead else min(options)
