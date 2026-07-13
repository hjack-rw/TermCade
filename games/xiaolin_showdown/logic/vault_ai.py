"""What the opponent does with a Wu's power at the vault — and, just as often, why it does nothing.

Fair, and that is the whole design constraint. The opponent reads only what a player sitting across
the table can read: both hands (they are face up), both point totals, the size of the pile, the size
of a personal deck. It never looks inside the pile or inside the player's deck. Where it cannot see,
it reasons about what is *likely* — the catalog is public, and so is what a Wu is worth.

Two of the new Wu therefore do nothing for it, and this is the honest reason:

**Diaskopia** (read the opponent's shelf) informs no decision the opponent makes. Nothing in
:mod:`bot` — not the challenge, not the wager, not what to field — turns on what the *player* has
shelved. Knowledge with no decision behind it is worth exactly nothing, so the opponent banks the
Falcon's Eye for its points. Give it a decision that depends on the player's future hand and the card
wakes up.

**Teleskopia** is worth only what it lets the opponent do differently, and under a one-action turn it
cannot look and then act: the Scope *is* the turn. Reading three Wu it can do nothing about buys it
nothing, so it banks the Eagle Scope too.

Both remain strong in a *player's* hand — a player carries the information forward across turns in
their head, which is a thing this opponent has no way to do. That asymmetry is real, and it is not a
bug: it is the difference between a mind and a policy.
"""

from __future__ import annotations

from dataclasses import dataclass

from .mechanics.powers import GAMBLE_SPREAD, Mechanic, is_gamble, mechanic_of
from .mechanics.scoring import initiative
from .models import Card, Player
from .settings import XiaolinSettings
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
# vault. It is a Wu for a Wu, and it *pays them* — so the thing it removes had better be a weapon.
REPULSION_THRESHOLD = 4


@dataclass(frozen=True)
class VaultPlay:
    """A Wu a duelist means to spend, and the answers its power will ask for."""

    card: Card
    priority: bool | None = None
    target: Card | None = None


def _me(state: XiaolinState, is_player: bool) -> Player:
    return state.player if is_player else state.bot


def _them(state: XiaolinState, is_player: bool) -> Player:
    return state.bot if is_player else state.player


def choose_vault_power(
    state: XiaolinState, settings: XiaolinSettings, *, is_player: bool = False
) -> VaultPlay | None:
    """The Wu this duelist spends this turn, or ``None`` to bank instead.

    Ordered by how decisive the power is, not by what it costs: a Wu that wins the next showdown is
    worth more than a Wu that banks two points, and a hand only gets one action to prove it.

    ``is_player`` is the *seat*, not the difficulty. It defaults to the opponent's, which is who plays
    by this in a real game — but every rule below is written as "my hand, their hand", so a simulation
    can sit a player in the same chair. Without that the harness only ever banked and drew, never spent
    a power, and every player win rate it reported was a floor.
    """
    for card in _me(state, is_player).whole_hand:
        mechanic = mechanic_of(card.power)

        if mechanic is Mechanic.REPULSION and _worth_shoving(state, settings, is_player):
            return VaultPlay(card, target=_their_best(state, is_player))

        if mechanic is Mechanic.TELEPATHEIA and _initiative_is_wrong(state, is_player):
            return VaultPlay(card, priority=_wants_initiative(state, is_player))

        if mechanic is Mechanic.ATTRACTION and _worth_reaching_for(state, is_player):
            return VaultPlay(card, target=_best_on_the_shelf(state, is_player))

        if mechanic is Mechanic.CHRONOKINESIS and _worth_drawing(state, settings, is_player):
            return VaultPlay(card)

        if mechanic is Mechanic.ANABIOSIS and _worth_reviving(state):
            return VaultPlay(card)

    return None


def expected_points(card: Card) -> float:
    """What banking a Wu pays, in expectation. The gamble Wu is the only one that isn't its face."""
    if is_gamble(card.power):
        low, high = GAMBLE_SPREAD
        return (low + high) / 2
    return float(card.points)


# --- the Ruby of Ramses: a Wu for a Wu, and it pays them --------------------------


def _their_best(state: XiaolinState, is_player: bool = False) -> Card:
    return max(_them(state, is_player).hand, key=duel_value)


def _worth_shoving(state: XiaolinState, settings: XiaolinSettings, is_player: bool = False) -> bool:
    """Shove their best Wu into their vault — unless the points would hand them the run.

    That is the trap the card carries: it is a denial that *pays the duelist you are denying*. Fire
    it while they are near the target and you lose the game with your own Wu.
    """
    them = _them(state, is_player)
    if len(them.hand) <= 1:  # a deposit may never empty a hand — theirs no more than yours
        return False
    best = _their_best(state, is_player)
    if them.points + expected_points(best) >= settings.point_limit:
        return False  # it would bank them into the win
    return duel_value(best) >= REPULSION_THRESHOLD


# --- the Mind Reader Conch: buy the initiative, when it is pointing the wrong way ---


def _wants_initiative(state: XiaolinState, is_player: bool = False) -> bool:
    """Does the opponent want to name the challenge, or to price the wager?

    Priority names the challenge; the duelist *without* it names the background and the stake. So a
    strong hand wants it and a weak one is glad to be rid of it — the Conch is spent on whichever
    answer the hands are not already giving.
    """
    me, them = _me(state, is_player), _them(state, is_player)
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


# --- the Glove of Jisaku: the best Wu on the shelf, not the top one ----------------


def _best_on_the_shelf(state: XiaolinState, is_player: bool = False) -> Card:
    return max(_me(state, is_player).deck, key=duel_value)


def _worth_reaching_for(state: XiaolinState, is_player: bool = False) -> bool:
    """Only when the shelf holds something a plain Draw would not have reached.

    A Draw costs the same action and costs no Wu. So the Glove has to buy a real upgrade over the
    top of the deck — otherwise it is two Wu spent to get one back.
    """
    shelf = _me(state, is_player).deck
    if not shelf:
        return False
    upgrade = duel_value(_best_on_the_shelf(state, is_player)) - duel_value(shelf[0])
    return upgrade >= ATTRACTION_MARGIN


# --- The Early Bird: a Wu off the pile, taken by being faster ----------------------


def choose_early_bird(
    state: XiaolinState, settings: XiaolinSettings, *, is_player: bool = False
) -> Card | None:
    """The Wu this duelist surrenders to outrun the other, or ``None`` to do something else.

    It reads the board a player can read and no more: it cannot see the Wu it is about to take (the
    pile is face down), so it is trading a *known* Wu for an unknown one, plus the turn's action.

    **Flying this is not free, and the simulation says so plainly.** An opponent that took it whenever
    it could lost ~8 points of win rate on the hard tier against one that never did (120 runs a tier).
    The reasons are the same three that price it for a player: the surrendered Wu is real, the *lead*
    it spends is what decides who names the challenge until it is rebuilt, and the action it costs
    could have banked points — and points, not Wu, are the win condition (see :func:`pick_deposit`,
    where the same lesson was measured).

    There is no cheap flight, either: the gap of three is barely reachable without a ±2 in hand, and
    the price is always your *highest*, so the Wu surrendered is essentially always a real one.

    So it flies as a **comeback**, not as an appetite: only while it is behind on points. Losing costs
    it nothing it was going to keep, and a fresh Wu off the pile is the fastest way back into the run.
    Ahead, it banks instead and lets the lead do its work.
    """
    from .actions import early_bird_options, initiative_lead  # local: actions imports this module

    me, them = _me(state, is_player), _them(state, is_player)
    spent = state.actions_taken if is_player else state.bot_actions_taken
    if spent >= settings.actions_per_turn or not state.card_deck:
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


# --- Anabiosis: the oldest Wu nobody won, back off the lost pile -------------------


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
    hand = _me(state, is_player).whole_hand
    chrono = next((c for c in hand if mechanic_of(c.power) is Mechanic.CHRONOKINESIS), None)
    if chrono is None:
        return False
    average_held = sum(duel_value(card) for card in hand) / len(hand)
    return duel_value(chrono) <= average_held
