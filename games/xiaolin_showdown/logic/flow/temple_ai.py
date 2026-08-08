"""The opponent's temple-power decisions — and it is fair: it reads only what a player across the table
could (both hands, both scores, pile size), never inside the pile or a personal deck.

Diaskopia is spent only by Jack, and only once (see `_worth_scouting`) — everyone else always banks
it, since nothing else yet reads reveal-memory of an opponent's deck. Teleskopia is different: every
duelist may fire it, and it re-fires as its own memory goes stale (see `_worth_scrying`) — the shared
pile's front card turns over fast, from either side's draw, prize, or Early Bird, so a one-time reveal
like Jack's would go stale almost immediately. `choose_early_bird` is its one consumer today.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import bot
from ..characters import jong
from ..characters.wuya import WITCH_EARLY_BIRD_GAP
from ..mechanics.powers import GAMBLE_SPREAD, Mechanic, is_gamble, mechanic_of
from ..mechanics.scoring import initiative
from ..schema.models import Card
from ..config.settings import XiaolinSettings, player_actions
from ..schema.state import XiaolinState
from .training import can_train, train_boost_step
from .turn import duel_value

# How much better the best Wu on the shelf must be than the one a plain Draw would hand over, before
# the Glove of Jisaku is worth *being spent* to reach it. A Draw costs the same action and costs no
# Wu, so the Glove has to buy a real upgrade, not a marginally better one.
ATTRACTION_MARGIN = 2

# What the oldest lost Wu must be worth before the opponent spends the Rooster on it. The Rooster
# pays two Wu (itself, and the action) for one it did not choose, so a scrap off the bottom of the
# lost pile is a worse deal than banking the Rooster and drawing. Set at the plain Wu's magnitude:
# it reaches for a real card, or it leaves the pile alone.
REVIVAL_MARGIN = 5

# How dangerous a Wu in the player's hand must be before the Ruby of Ramses shoves it into their
# temple. It is a Wu for a Wu, and it *pays them* — so the thing it removes had better be a weapon.
REPULSION_THRESHOLD = 4

# How much the OTHER hand must be worth, over this one, before the Lantern is spent on the swap.
# The Lantern banks for real points, so a marginal upgrade is a worse deal than banking it — the
# swap has to steal a lead, not tidy one.
SWAP_MARGIN = 5


@dataclass(frozen=True)
class TemplePlay:
    """A Wu a duelist means to spend, and the answers its power will ask for."""

    card: Card
    priority: bool | None = None
    target: Card | None = None
    to_deck: bool = False  # Repulsion: shove into their deck (no points) rather than their temple


def choose_temple_power(
    state: XiaolinState, settings: XiaolinSettings, *, is_player: bool = False
) -> TemplePlay | None:
    """The Wu this duelist spends this turn, or ``None`` to bank instead.

    Ordered by how decisive the power is, not by what it costs: a Wu that wins the next showdown is
    worth more than a Wu that banks two points, and a hand only gets one action to prove it.

    ``is_player`` is the *seat*, not the difficulty. It defaults to the opponent's, which is who plays
    by this in a real game — but every rule below is written as "my hand, their hand", so a simulation
    can sit a player in the same chair.
    """
    for card in state.duelist(is_player).whole_hand:
        mechanic = mechanic_of(card.power)

        if mechanic is Mechanic.BOUNCE and _worth_shoving(state, is_player):
            return TemplePlay(
                card,
                target=_their_best(state, is_player),
                to_deck=_shove_to_deck(state, settings, is_player),
            )

        if mechanic is Mechanic.ENHANCED_VISION and _initiative_is_wrong(state, is_player):
            return TemplePlay(card, priority=_wants_initiative(state, is_player))

        if mechanic is Mechanic.FETCH and _worth_reaching_for(state, is_player):
            return TemplePlay(card, target=_best_on_the_shelf(state, is_player))

        if mechanic is Mechanic.DRAW and _worth_drawing(state, settings, is_player):
            return TemplePlay(card)

        if mechanic is Mechanic.LUCK and _worth_reviving(state):
            return TemplePlay(card)

        if mechanic is Mechanic.WISH and _worth_wishing(state, is_player):
            return TemplePlay(card, target=_best_wishable(state, is_player))

        if mechanic is Mechanic.TRANSFER and _worth_swapping(state, is_player):
            return TemplePlay(card)

        if mechanic is Mechanic.PROGNOSIS and _worth_foreseeing(state, is_player):
            return TemplePlay(card)

        if mechanic is Mechanic.REFRESH and _worth_refreshing(state):
            return TemplePlay(card)

        if mechanic is Mechanic.TRAIN_BOOST and _worth_summoning_to_train(state, settings, card, is_player):
            return TemplePlay(card)

        if mechanic is Mechanic.READ_DECK and _worth_scouting(state, is_player):
            return TemplePlay(card)

        if mechanic is Mechanic.SCRY and _worth_scrying(state, is_player):
            return TemplePlay(card)

    return None


def _worth_summoning_to_train(
    state: XiaolinState, settings: XiaolinSettings, card: Card, is_player: bool = False
) -> bool:
    """Spend a summon Wu at the temple only when its shove COMPLETES the training bar.

    A summon Wu is worth more fielded than fed to a half-full bar — but a shove that finishes a level
    pays out a stat on the spot, a permanent gain nothing else this turn can match, and never a wasted
    partial fill. The Sapphire Dragon's full-bar boost always qualifies (and it can never be fielded, so
    the temple is its only use); a lower tier only near the top of the bar. Never on the last card in hand.
    """
    me = state.duelist(is_player)
    if not can_train(me, settings) or me.just_trained or len(me.hand) <= 1:
        return False
    step = train_boost_step(card.power.train_step, settings, is_player=is_player)
    train_length = settings.train_length_player if is_player else settings.train_length_bot
    return me.training + step >= train_length


def _worth_scouting(state: XiaolinState, is_player: bool = False) -> bool:
    """Diaskopia, for Jack alone: fire it once, early, purely to seed reveal-memory for his own
    steal — not gated on his hand thinning out, just the first turn he holds one and still knows
    nothing. The reveal itself writes `known_of_opponent_deck` (see `power_effects._read_deck`); once
    that is non-empty this stops re-triggering on its own. Every other duelist still always banks it —
    nothing else reads reveal-memory yet, so scouting would only cost them the card's points for
    nothing (see the module docstring)."""
    me, them = state.duelist(is_player), state.opponent(is_player)
    return bot.is_jack(me) and not me.known_of_opponent_deck and bool(them.deck)


def _worth_scrying(state: XiaolinState, is_player: bool = False) -> bool:
    """Teleskopia, for any duelist: fire whenever the memory of the pile's front has gone stale.

    Unlike Diaskopia's one-time scout, this re-fires — the shared pile's front card turns over fast
    (either side's draw, prize, or Early Bird can consume it), so a single reveal would go stale almost
    immediately. The reveal writes `known_upcoming_pile` (see `power_effects._scan_pile`);
    `choose_early_bird` is what reads it, and stops this re-triggering for as long as it still holds.
    """
    me = state.duelist(is_player)
    return bool(state.card_deck) and state.card_deck[0].id not in me.known_upcoming_pile


def _worth_swapping(state: XiaolinState, is_player: bool = False) -> bool:
    """Spend the Lantern when the other hand is the better arsenal by a real margin.

    Summed ``duel_value``, this hand's Lanterns excluded — the spent one leaves with the swap, so
    it was never part of what is being traded away.
    """
    me, them = state.duelist(is_player), state.opponent(is_player)
    if not them.hand:
        return False
    mine = sum(
        duel_value(card)
        for card in me.hand
        if mechanic_of(card.power) is not Mechanic.TRANSFER
    )
    theirs = sum(duel_value(card) for card in them.hand)
    return theirs - mine >= SWAP_MARGIN


def expected_points(card: Card) -> float:
    """What banking a Wu pays, in expectation. The gamble Wu is the only one that isn't its face."""
    if is_gamble(card.power):
        low, high = GAMBLE_SPREAD
        return (low + high) / 2
    return float(card.points)


# --- the Ruby of Ramses: a Wu for a Wu, and it pays them --------------------------


def _their_best(state: XiaolinState, is_player: bool = False) -> Card:
    return max(state.opponent(is_player).hand, key=duel_value)


def _worth_shoving(state: XiaolinState, is_player: bool = False) -> bool:
    """Shove their best Wu — if it is a real weapon and their hand can spare one.

    Whether the *points* are safe is no longer part of this: with the deck as a destination, a shove
    that would bank them into the win is simply routed there instead (see `_shove_to_deck`).
    """
    them = state.opponent(is_player)
    if len(them.hand) <= 1:  # a deposit may never empty a hand — theirs no more than yours
        return False
    return duel_value(_their_best(state, is_player)) >= REPULSION_THRESHOLD


def _shove_to_deck(state: XiaolinState, settings: XiaolinSettings, is_player: bool = False) -> bool:
    """Deck it, not deposit it, when the points would carry them toward the win.

    Deposit is the aggressive line — the weapon is gone for good — and worth the points it pays for a
    real threat. But the card's trap is that those points are *theirs*: near the limit, banking their
    own Wu could hand them the run. There, the deck denies the weapon for a while and pays them nothing.
    """
    them = state.opponent(is_player)
    return them.points + expected_points(_their_best(state, is_player)) >= state.win_target(settings)


# --- the Mind Reader Conch: buy the initiative, when it is pointing the wrong way ---


def _wants_initiative(state: XiaolinState, is_player: bool = False) -> bool:
    """Does the opponent want to name the challenge, or to price the wager?

    Priority names the challenge; the duelist *without* it names the background and the stake. So a
    strong hand wants it and a weak one is glad to be rid of it — the Conch is spent on whichever
    answer the hands are not already giving.
    """
    me, them = state.duelist(is_player), state.opponent(is_player)
    my_stats, their_stats = jong.battle_stats(me), jong.battle_stats(them)
    edges = [
        my_stats[stat]
        + max((card.stats[stat] or 0 for card in me.hand), default=0)
        - their_stats[stat]
        for stat in my_stats
    ]
    return max(edges, default=0) > 0


def _initiative_is_wrong(state: XiaolinState, is_player: bool = False) -> bool:
    """Would the coming showdown hand priority to the wrong duelist?

    Both hands are face up, so the opponent can read the initiative it is about to get. It only
    spends the Conch when that reading disagrees with what it wants — a Wu spent to buy what you were
    getting for free is a Wu thrown away.
    """
    player_bonus, bot_bonus = initiative(state.player, state.bot)
    mine, theirs = (player_bonus, bot_bonus) if is_player else (bot_bonus, player_bonus)
    if mine == theirs:
        return True  # a tie is a coin toss, and a coin toss is always worth buying out of
    return (mine > theirs) is not _wants_initiative(state, is_player)


def _worth_foreseeing(state: XiaolinState, is_player: bool = False) -> bool:
    """Prognosis: let the opponent lead the showdown, but keep the challenger's ground (win the level
    battles). Worth spending only when this duelist would NOT hold that ground on its own — its
    initiative does not already lead. Holding the lead, the Conch would trade it for a ground it has."""
    player_bonus, bot_bonus = initiative(state.player, state.bot)
    mine, theirs = (player_bonus, bot_bonus) if is_player else (bot_bonus, player_bonus)
    return mine <= theirs


# What the most-recently-used Wu must be worth before Refresh reclaims it. The Reverso is a Wu (worth
# its points banked) and the turn's action, so what it calls back had better be a real weapon.
REFRESH_MARGIN = 5


def _worth_refreshing(state: XiaolinState) -> bool:
    """Refresh: the Wu most recently used by either duelist, back to hand. Only when that Wu is worth
    reclaiming — a scrap is a Wu and an action spent for nothing."""
    return bool(state.used) and duel_value(state.used[-1]) >= REFRESH_MARGIN


# --- the Glove of Jisaku: the best Wu on the shelf, not the top one ----------------


def _best_on_the_shelf(state: XiaolinState, is_player: bool = False) -> Card:
    return max(state.duelist(is_player).deck, key=duel_value)


def _worth_reaching_for(state: XiaolinState, is_player: bool = False) -> bool:
    """Only when the shelf holds something a plain Draw would not have reached.

    A Draw costs the same action and costs no Wu. So the Glove has to buy a real upgrade over the
    top of the deck — otherwise it is two Wu spent to get one back.
    """
    shelf = state.duelist(is_player).deck
    if not shelf:
        return False
    upgrade = duel_value(_best_on_the_shelf(state, is_player)) - duel_value(shelf[0])
    return upgrade >= ATTRACTION_MARGIN


# --- The Early Bird: a Wu off the pile, taken by being faster ----------------------

# A mechanic constant, not a player setting — the same margin the pool's own numbers are priced
# against. Wuya's own version lives beside her, in `WITCH_EARLY_BIRD_GAP`.
EARLY_BIRD_GAP = 3


def early_bird_gap(state: XiaolinState, *, is_player: bool) -> int:
    """The initiative lead needed to fly the Early Bird — a mechanic constant, not a player setting;
    shortened for Wuya, whose sense finds the moment for her. Everyone else pays it in full."""
    me = state.duelist(is_player)
    if mechanic_of(me.character.power) is Mechanic.WITCHCRAFT:
        return min(EARLY_BIRD_GAP, WITCH_EARLY_BIRD_GAP)
    return EARLY_BIRD_GAP


def choose_early_bird(
    state: XiaolinState, settings: XiaolinSettings, *, is_player: bool = False
) -> Card | None:
    """The Wu surrendered to outrun the other duelist, or ``None``.

    Flown only as a comeback (behind on points): it costs a real Wu, the initiative lead that names
    the challenge, and the turn's action — and points are the win condition. Blind by default (the
    prize taken is never weighed, only what's given up) — a Teleskopia already fired legitimately
    turns that into a known quantity, and a confirmed worse trade is vetoed (see `known_upcoming_pile`).
    """
    from .actions import early_bird_options, initiative_lead  # local: actions imports this module

    me, them = state.duelist(is_player), state.opponent(is_player)
    spent = state.actions_spent(is_player)
    # Each side flies against its own budget — in a boss run the player's is the larger one.
    budget = player_actions(state, settings) if is_player else settings.actions_per_turn_bot
    if spent >= budget or not state.card_deck:
        return None
    if initiative_lead(state, is_player=is_player) < early_bird_gap(state, is_player=is_player):
        return None
    if me.points >= them.points:
        return None  # ahead, or level: bank the points and keep the speed that names the challenge

    options = early_bird_options(state, is_player=is_player)
    if not options:
        return None

    # Give up the cheapest of the Wu tied at the top — they all cost the same speed, so let go of the
    # one that fights worst.
    cheapest = min(options, key=duel_value)
    if duel_value(cheapest) > EARLY_BIRD_CEILING:
        return None  # its fastest Wu is also a weapon: keep it, and win the Wu the honest way

    front = state.card_deck[0]
    if front.id in me.known_upcoming_pile and duel_value(front) < duel_value(cheapest):
        return None  # Teleskopia already showed what's there — a known worse Wu isn't the honest trade

    return cheapest


# What the surrendered Wu may be worth in a showdown before the opponent would rather duel for the
# prize than buy it. Kept at the plain Wu's magnitude because that is what it *means* — the comeback
# rule above is what actually decides this, not this ceiling.
EARLY_BIRD_CEILING = 5


# --- Euthymia: the oldest Wu nobody won, back off the lost pile -------------------


def _worth_reviving(state: XiaolinState) -> bool:
    """Only when the Wu it would call back beats what the same action would otherwise buy.

    The Rooster costs an action *and* itself, and what comes back is not chosen — it is whatever was
    lost first. So it has to beat a plain Draw, which costs the action alone. Fired at an empty lost
    pile it fizzles, and an action fizzled is an action gone.
    """
    if not state.lost:
        return False
    return duel_value(state.lost[0]) >= REVIVAL_MARGIN


# --- The Blind Swordsman's Treasurebox: a chosen Wu, pulled from either Vault -----------------------

# How good the best Vault target must be before the Treasurebox is worth spending on it. Set a step
# above REVIVAL_MARGIN: unlike Euthymia's blind pull off a modest Rooster, this pull is CHOSEN — the
# single best Wu in either Vault — but the Wu spent to buy it is a real 10-point Treasurebox, not a
# booster nobody would miss.
WISH_MARGIN = 6


def _best_wishable(state: XiaolinState, is_player: bool = False) -> Card:
    """The strongest Wu either Vault holds — the caster's own, or the one the opponent already
    banked. Reaching into the opponent's is the card's real strength (see `power_effects._restore`);
    reaching into your own is just undoing an already-paid deposit, so this never prefers one Vault
    over the other on its own — only whichever single Wu fights best."""
    me, them = state.duelist(is_player), state.opponent(is_player)
    return max(me.vault + them.vault, key=duel_value)


def _worth_wishing(state: XiaolinState, is_player: bool = False) -> bool:
    """Spend the Treasurebox only when the best Wu either Vault holds is a real weapon — fizzles with
    nothing to reach for in either Vault."""
    me, them = state.duelist(is_player), state.opponent(is_player)
    if not (me.vault or them.vault):
        return False
    return duel_value(_best_wishable(state, is_player)) >= WISH_MARGIN


# --- Chronokinesis: a Wu off the pile, sight unseen --------------------------------


def _worth_drawing(state: XiaolinState, settings: XiaolinSettings, is_player: bool = False) -> bool:
    """Trade this Wu for whatever the pile is holding.

    Chronokinesis costs a Wu and returns a Wu, so the hand never grows — it is a *swap*, and it is
    priced as one: would an unknown Wu be worth more in a showdown than the one being spent for it?

    Nobody looks into the pile. It compares the Wu against the hand it is holding, which is a fair
    stand-in for what an unknown Wu is worth and needs nothing it is not allowed to see: a
    Chronokinesis that is already the weakest thing you hold is a Wu you can only improve on.
    """
    if not state.card_deck:
        return False
    hand = state.duelist(is_player).whole_hand
    chrono = next((c for c in hand if mechanic_of(c.power) is Mechanic.DRAW), None)
    if chrono is None:
        return False
    average_held = sum(duel_value(card) for card in hand) / len(hand)
    return duel_value(chrono) <= average_held
