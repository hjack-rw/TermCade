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

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import replace

from termcade.core.rng import Rng

from .battle import Ground, Round, score_battle
from ..schema.constants import ELEMENTS, OPPOSITES, TOURNAMENT
from ..mechanics.powers import Mechanic, chooses_element, is_uncontrolled, mechanic_of, names_a_stat
from ..mechanics.resolve import as_boost, resolve_played_power
from ..schema.models import Card, Player
from .turn import duel_value


def is_jack(player: Player) -> bool:
    """Whether this duelist holds a permanent Jack-Bot boost — Jack Spicer, and only him: the
    mechanic is his alone (see ``xs_game.sql``'s powers -8 and 0 — his character and his card,
    the same split as Hannibal's Elemental Manipulation and Moby Morpher)."""
    return mechanic_of(player.character.power) is Mechanic.BOT


def is_chase(player: Player) -> bool:
    """Whether this duelist gifts a won prize — Chase Young, the boss who refuses the Wu."""
    return mechanic_of(player.character.power) is Mechanic.BEAST_FORM


def is_hannibal(player: Player) -> bool:
    """Whether this duelist deflects the elements — Hannibal, bare-handed. His Elemental
    Manipulation rides on his character (his shown power stays the Morpher), so it keys off the
    character, the way summons do, not a mechanic he can hold only one of."""
    return player.character.name == "Hannibal_Roy_Bean"


def is_jong(player: Player) -> bool:
    """Is this duelist wearing the construct right now."""
    return player.jong_form


def steal_target(
    hand: Sequence[Card], *, prefer: Callable[[Card], bool] | None = None
) -> Card | None:
    """AI Jack's steal: the strongest Wu in the opponent's hand — fully known, so judged like any
    other bot decision. ``None`` on an empty hand: the opponent's deck is never handed to this
    function at all, so a blind fallback can't be ranked by content even by accident — the caller
    (``duel._resolve_ai_jack_steal``) picks blind from the deck itself when this returns ``None``.

    ``prefer`` narrows the field before ranking, when it matches anything — Jack's own steal passes
    ``jack.is_counter`` so a Denshi Bunny in hand is taken outright, even over a numerically stronger
    Wu; Sands of Time (open to anyone) leaves it unset and ranks the whole hand as before.
    """
    if not hand:
        return None
    pool = [c for c in hand if prefer(c)] if prefer is not None else []
    return max(pool or hand, key=duel_value)


def best_known_deck_card(known: Sequence[Card]) -> Card:
    """The steal's blind-fallback ranking: the best of a set of deck cards already confirmed real —
    never guessed at (see ``Player.known_of_opponent_deck``). Takes only the pre-filtered subset the
    caller has already confirmed is known, the same way ``steal_target`` never sees a whole deck: this
    module ranks what it is handed, and is never the one deciding what counts as known."""
    return max(known, key=duel_value)


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


# STEAL/SEIZE_GROUND: their whole value is a side-effect `_after`'s battle score cannot see — the
# opponent's own best hand card, or the challenger's seat for the rest of the showdown. A card built
# entirely around one of these prints low or no stats, so it reads as a weak pick next to any real
# stat stick and never gets fielded on purpose. `choose_card` reaches for one after the stat-best pick
# is known, but only when it doesn't cost the battle — or the prize — itself.
#
# HACK (Denshi Bunny) is deliberately NOT here: its whole value is denying Jack a bot identity, and
# Jack is never player-selectable (`is_playable=0` in the seed) — the bot can never face him as an
# opponent, so a "prefer HACK against a hackable opponent" heuristic would have no live trigger to
# fire from. Checked, not assumed.
_SIDE_EFFECT_MECHANICS = frozenset({Mechanic.STEAL, Mechanic.SEIZE_GROUND})


def _worth_the_side_effect(card: Card, ground: Ground, *, is_player: bool) -> bool:
    """Whether ``card``'s side-effect is actually live this battle, not just present in hand.

    STEAL is always a fair trade in isolation — it takes the opponent's own strongest hand Wu, or a
    blind deck pull, never something picked against the stealer. SEIZE_GROUND is only worth taking
    when the acting side doesn't already hold the ground it would seize.
    """
    mechanic = mechanic_of(card.power)
    if mechanic is Mechanic.STEAL:
        return True
    if mechanic is Mechanic.SEIZE_GROUND:
        return is_player != ground.challenger_is_player
    return False


def _costs_the_battle_or_prize(
    key: tuple[int, int], best_key: tuple[int, int], *, prize_bar: int
) -> bool:
    """Whether switching from the stat-best pick to a side-effect card gives up something real.

    Two ways it can: flipping a win-or-tie into a loss (``key[0]`` crosses zero), or giving up a
    decisive-blow prize claim the stat-best pick would have made — its own blow (``-best_key[1]``)
    clears ``prize_bar`` (``settings.prize_threshold + 1``) but the side-effect card's own blow
    (``-key[1]``) does not. If BOTH clear it, nothing is actually given up, so switching is still free.
    The broader prize routes (a win on two fronts, total command, being in tune) read the WHOLE
    showdown, which a single battle's trial has no way to see — this only guards the one route a
    single battle decides outright.
    """
    if best_key[0] > 0:
        return False  # the stat-best pick was already losing; nothing left to protect
    if key[0] > 0:
        return True  # flips a win-or-tie into a loss
    return -best_key[1] >= prize_bar > -key[1]


def choose_card(
    battle: Round,
    ground: Ground,
    playable: Sequence[Card],
    rng: Rng,
    *,
    is_player: bool = False,
    prize_bar: int = 8,
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
    ``prize_bar`` is ``prize_threshold + 1`` — the blow a decisive win must clear (default matches
    ``XiaolinSettings``'s own default threshold, 7); the real caller passes its own settings' value.

    Once the stat-best pick is known, a live STEAL/SEIZE_GROUND is taken over it instead — but only
    when doing so doesn't flip a win-or-tie into a loss, or give up a decisive-blow prize claim the
    stat-best pick would have made (see ``_costs_the_battle_or_prize``).
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
    if best is None or best_key is None:
        return rng.choice(list(playable))

    side_effect = _side_effect_pick(
        playable, battle, ground, best, best_key, is_player=is_player, prize_bar=prize_bar
    )
    return side_effect if side_effect is not None else best


def _side_effect_pick(
    playable: Sequence[Card],
    battle: Round,
    ground: Ground,
    best: Card,
    best_key: tuple[int, int],
    *,
    is_player: bool,
    prize_bar: int,
) -> Card | None:
    """The first live STEAL/SEIZE_GROUND in ``playable`` that doesn't cost the battle or the prize —
    see ``choose_card``'s own docstring for why it's preferred over the stat-best pick at all."""
    for card in playable:
        if card is best or mechanic_of(card.power) not in _SIDE_EFFECT_MECHANICS:
            continue
        if not _worth_the_side_effect(card, ground, is_player=is_player):
            continue
        key = _after(battle, ground, card, is_player=is_player)
        if not _costs_the_battle_or_prize(key, best_key, prize_bar=prize_bar):
            return card
    return None


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
    cost. The bot fields the Heart as a plain 2/2/2 instead.

    Jack-Bot is never boosted here either: it curses the *opponent*, and "what it makes reachable"
    only ever measures the caster's own side. See `characters.jack.choose_jack_bot`, decided
    separately before this is even called.
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


def choose_element(battle: Round, ground: Ground, card: Card, *, is_player: bool = False) -> str:
    """Which element the Morpher, Eye of Dashi or Monsoon Sandals names.

    Played out exactly like ``choose_stat``: every element is fielded in a trial battle and the one
    that leaves the board best is taken, rather than defaulting to the arena already in play.
    """
    return min(
        ELEMENTS,
        key=lambda element: _after(battle, ground, card, is_player=is_player, element=element),
    )


def _after(
    battle: Round,
    ground: Ground,
    card: Card,
    *,
    is_player: bool,
    stat: str | None = None,
    element: str | None = None,
) -> tuple[int, int]:
    """How the battle stands once ``card`` is fielded. Lower is better *for the duelist fielding it*.

    ``(score, -blow)``: the score first, because winning the battle is what wins the showdown, and
    the size of the blow only to separate fields that win by the same margin. A battle's score is
    signed from the player's side, so the player maximises it and the bot minimises it.

    A Wu that names a stat is worth what its *best* stat is worth — so weighing whether to play it at
    all (``choose_card``) asks this without a stat, and gets the best line it could take. A Wu that
    names an element (``chooses_element``) is weighed the same way, over every element in turn.
    """
    if stat is None and names_a_stat(card.power):
        return min(
            _after(battle, ground, card, is_player=is_player, stat=option, element=element)
            for option in _stat_options(ground, card)
        )
    if element is None and chooses_element(card.power):
        return min(
            _after(battle, ground, card, is_player=is_player, stat=stat, element=option)
            for option in ELEMENTS
        )

    trial = deepcopy(battle)
    effect = resolve_played_power(
        trial, card, is_player=is_player,
        element=element if element is not None else ground.background, stat=stat,
    )
    background = ground.background
    if effect and effect.startswith("background:"):
        background = effect.split(":", 1)[1]  # a Monsoon Sandals candidate recolours the arena
    terms = replace(
        ground,
        background=background,
        bonus_cancelled=ground.bonus_cancelled or effect == "cancel",
        bonus_reversed=ground.bonus_reversed or effect == "reverse",
    )
    if effect and effect.startswith("conduct:"):
        # Conduct is newly active — `ground` carries no swing for it yet (the real Duel's own
        # `_conduct_bonus` reads 0 while `conduct_caster` is unset), so the WHOLE current table's
        # swing becomes the caster's bonus for the first time, this card included.
        terms = _conduct_swing(trial, terms, is_player=is_player, net=_conduct_net(trial, terms))
    elif trial.conduct_caster is not None:
        # A Shard of Lightning fielded EARLIER this same battle (a multi-Wu wager) is still active,
        # and `ground` already carries its swing so far (`Duel._ground` re-bakes it every cycle) —
        # only THIS candidate's own marginal element shifts it further, not the whole net again.
        delta = 1 if card.element == "metal" else (-1 if card.element else 0)
        terms = _conduct_swing(trial, terms, is_player=trial.conduct_caster, net=delta)
    score_battle(trial, terms)
    sign = -1 if is_player else 1
    return sign * trial.score, -_blow(trial, terms, is_player=is_player)


def _conduct_net(trial: Round, terms: Ground) -> int:
    """The whole table's metal swing, read fresh — every Wu on either side plus the arena, the same
    count `duel.Duel._conduct_bonus` makes when Shard of Lightning first goes active."""
    net = sum(
        1 if card.element == "metal" else (-1 if card.element else 0)
        for card in trial.player.queue + trial.bot.queue
    )
    if terms.background:
        net += 1 if terms.background == "metal" else -1
    return net


def _conduct_swing(trial: Round, terms: Ground, *, is_player: bool, net: int) -> Ground:
    """Add ``net`` to whoever cast Shard of Lightning's own base on the trial's contested stat —
    ``is_player`` is whoever CAST it, not necessarily who just played the candidate card being
    weighed, so the swing lands on the right side's base stats whichever of them cast it."""
    if not trial.stat or not net:
        return terms
    if is_player:
        base = dict(terms.player_stats)
        if trial.stat in base:
            base[trial.stat] += net
        return replace(terms, player_stats=base)
    base = dict(terms.bot_stats)
    if trial.stat in base:
        base[trial.stat] += net
    return replace(terms, bot_stats=base)


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

    # The swing at width w is `w * (2P - 1)`, monotone in w — so only the *sign* of the margin
    # matters, not its scale: take the widest field still ahead, else the narrowest on offer.
    ahead = [width for width in options if margin(width) > 0]
    return max(ahead) if ahead else min(options)
