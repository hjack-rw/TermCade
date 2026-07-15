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

from .battle import Ground, Round, score_battle
from .constants import OPPOSITES, TOURNAMENT
from .mechanics.powers import names_a_stat
from .mechanics.resolve import resolve_played_power
from .models import Card
from .turn import duel_value


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
    opposite, otherwise counter the player's most common element."""
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
    """
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
    voided = resolve_played_power(
        trial, card, is_player=is_player, element=ground.background, stat=stat
    )
    terms = replace(ground, bonus_cancelled=ground.bonus_cancelled or voided)
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
        mine.queue.append(deepcopy(boost))  # the resolver reads a live boost off the tail
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
    # That is the expected-swing rule written out. The swing is `w x (2P - 1)`, and any sane reading of
    # a margin into a chance is monotone — so the best width turns on the *sign* of the margin, never on
    # the scale you map it through. (This was written with a `WAGER_SPREAD` constant first. Swept from 2
    # to 40 it changed not one decision in a full run, because it could not: it divided every width by
    # the same number. A knob that cannot move anything is worse than no knob, so it is gone.)
    ahead = [width for width in options if margin(width) > 0]
    return max(ahead) if ahead else min(options)
