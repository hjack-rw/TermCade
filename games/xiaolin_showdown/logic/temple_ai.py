"""The opponent's temple-power decisions — and it is fair: it reads only what a player across the table
could (both hands, both scores, pile size), never inside the pile or a personal deck.

Diaskopia and Teleskopia are always banked, never spent: no decision here turns on the player's shelf,
and a one-action turn cannot look *and* act. Give either one a decision and it wakes up.
"""

from __future__ import annotations

from dataclasses import dataclass

from .mechanics.powers import GAMBLE_SPREAD, Mechanic, is_gamble, mechanic_of
from .mechanics.scoring import initiative
from .models import Card
from .settings import XiaolinSettings, player_actions
from .state import XiaolinState
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

# What the oldest lost Wu must be worth before Wuya's witchcraft spends her temple action on the
# recall. She pays no Wu (unlike the Rooster), so the bar sits under REVIVAL_MARGIN — but an action
# is still a deposit not made, and a scrap is not worth one.
WITCH_RECALL_MARGIN = 3


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
    can sit a player in the same chair. Without that the harness only ever banked and drew, never spent
    a power, and every player win rate it reported was a floor.
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

        if mechanic is Mechanic.TRANSFER and _worth_swapping(state, is_player):
            return TemplePlay(card)

        if mechanic is Mechanic.PROGNOSIS and _worth_foreseeing(state, is_player):
            return TemplePlay(card)

        if mechanic is Mechanic.REFRESH and _worth_refreshing(state):
            return TemplePlay(card)

    return None


def worth_recalling(state: XiaolinState) -> bool:
    """Wuya's recall: the lost pile's OLDEST (Euthymia's rule), against the action it costs."""
    return bool(state.lost) and duel_value(state.lost[0]) >= WITCH_RECALL_MARGIN


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
    return them.points + expected_points(_their_best(state, is_player)) >= settings.point_limit


# --- the Mind Reader Conch: buy the initiative, when it is pointing the wrong way ---


def _wants_initiative(state: XiaolinState, is_player: bool = False) -> bool:
    """Does the opponent want to name the challenge, or to price the wager?

    Priority names the challenge; the duelist *without* it names the background and the stake. So a
    strong hand wants it and a weak one is glad to be rid of it — the Conch is spent on whichever
    answer the hands are not already giving.
    """
    me, them = state.duelist(is_player), state.opponent(is_player)
    edges = [
        me.character.stats[stat]
        + max((card.stats[stat] or 0 for card in me.hand), default=0)
        - them.character.stats[stat]
        for stat in me.character.stats
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


def choose_early_bird(
    state: XiaolinState, settings: XiaolinSettings, *, is_player: bool = False
) -> Card | None:
    """The Wu surrendered to outrun the other duelist, or ``None``.

    Flown only as a comeback (behind on points). An opponent that took it whenever it could lost ~8
    points of hard-tier win rate over 120 runs a tier: it costs a real Wu, the initiative lead that
    names the challenge, and the turn's action — and points are the win condition.
    """
    from .actions import early_bird_options, initiative_lead  # local: actions imports this module

    me, them = state.duelist(is_player), state.opponent(is_player)
    spent = state.actions_spent(is_player)
    # Each side flies against its own budget — in a boss run the player's is the larger one.
    budget = player_actions(state, settings) if is_player else settings.actions_per_turn
    if spent >= budget or not state.card_deck:
        return None
    if initiative_lead(state, is_player=is_player) < settings.early_bird_gap:
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
    return cheapest


# What the surrendered Wu may be worth in a showdown before the opponent would rather duel for the
# prize than buy it. Measured across 3/4/5: at 3 the opponent never flies at all (reaching the gap
# needs a ±2, and the price is always your highest, so a "cheap" flight does not exist), and at 4 and
# 5 it plays identically. It is kept at the plain Wu's magnitude because that is what it *means* — do
# not read the number as a live knob; the comeback rule above is what actually decides this.
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
