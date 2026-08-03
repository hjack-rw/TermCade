"""What a battle is, and how it is weighed.

Pure and free of the stage machine, so :mod:`.bot` can reach it: the duel scores a battle to find
who won, the bot scores a hypothetical one to find what to play, and there is one scorer for both.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field

from .mechanics.cards import excluding, is_one_of
from .mechanics.powers import is_boost_slot
from .mechanics.scoring import contributing, count_end_stats
from .models import Card


@dataclass
class Side:
    """One duelist's half of a battle: what they put on the table, and what landed on them.

    Nothing here knows *which* duelist it belongs to, so a rule written against a ``Side`` is
    written once and holds for both.
    """

    queue: list[Card] = field(default_factory=list)  # what scores on this side
    suffered: list[Card] = field(default_factory=list)  # curse mirrors the opponent landed here
    amplifiers: list[Card] = field(default_factory=list)  # which of those mirrors a booster doubled
    jack_bot: list[Card] = field(default_factory=list)  # which of those mirrors came from Jack-Bot's
    # boost-slot curse rather than a played card — joins "&" on the board like Jong's Heart, never "+"
    spent: list[Card] = field(default_factory=list)  # own copies emptied onto a curse, shown opposite
    result: list[int] = field(default_factory=list)  # per-stat end values

    # What has been negated on this side, for this battle only. A negated line is *absent*, not
    # zeroed: its cards lend no stats and read no element, so they earn no background bonus either.
    #   base     — a Sphere of Jianyu: this duelist's character counts for nothing
    #   offence  — an Emperor Scorpion: every Wu this duelist played counts for nothing
    #   defence  — a Reversing Mirror: every curse landed here counts for nothing
    # They are read at scoring time rather than applied when played, so a Wu fielded *after* the
    # negator is negated too — a three-Wu wager is laid down one at a time, and the order a duelist
    # happened to choose must not decide what survives.
    base_negated: bool = False
    offence_negated: bool = False
    defence_negated: bool = False
    boost_negated: bool = False  # a Star Hanabi — this side's boost lends no stats
    # A Kuzusu Atom / Eye of Dashi has set what element this side's Wu count as, for the background
    # bonus only (their stats are untouched). ``None`` leaves each Wu its own printed element.
    element_as: str | None = None
    # Two element-setters disagreed over this side (a Set-Element and a Cleanse, say): they cancel,
    # `element_as` reverts to None, and this flags it so the showdown story can say why.
    element_cancelled: bool = False
    # Ward Wu (Monkey Staff and kin) protect this side's Wu OF THEIR ELEMENT from every negative
    # elemental bonus this showdown — the opposite arena's drag and metal's alike. Lift still lands.
    # A set: field two wards of different elements and both protect, they do not overwrite each other.
    ward: set[str] = field(default_factory=set)
    # A stat-shield Wu (Mikado Arms and kin) fielded here: its caster takes no curse on these stats —
    # a debuff landed on a shielded stat counts nothing. One entry per shield Wu fielded.
    shielded: set[str] = field(default_factory=set)
    # Whether this duelist fights this battle as a construct — Mala Mala Jong, or Jack in any of his
    # three identity swaps (see `duel.Duel._is_construct`). No mechanic reads this yet; it exists so
    # a future auto-win-vs-construct Wu has a flag to key off, instead of re-deriving the question.
    is_construct: bool = False

    def mine(self) -> list[Card]:
        """Every Wu *this* duelist put on the table — what the board owes them a line for.

        Not the same question as what still moves a stat. A booster fielded as an ordinary Wu lends
        nothing and a curse's caster empties their own copy onto the victim, but only the second is
        absent from this side: its mirror is printed on the opponent's, so printing it here too would
        count it twice. Everything else was staked, and a staked Wu the board never shows cannot be
        told from one that was never played.
        """
        return excluding(self.queue, self.suffered + self.spent)

    def contributors(self) -> list[Card]:
        """The Wu this duelist played that still contribute — all the background rewards.

        A curse mirror in the queue is the opponent's Wu. It reads the background too, but against
        this side — see ``suffers_bonus`` in :func:`~.mechanics.scoring.count_end_stats`.
        """
        if self.offence_negated:
            return []
        played = contributing(excluding(self.queue, self.suffered))
        if self.boost_negated:  # a fielded boost keeps its real power; a played Wu wears a neutral one
            played = [card for card in played if not is_boost_slot(card.power)]
        return played

    def curses(self) -> list[Card]:
        """The curses still biting this duelist — none, once a Reversing Mirror has turned them."""
        if self.defence_negated:
            return []
        return contributing(self.suffered)

    def counted(self) -> list[Card]:
        """Every card whose stats still reach the score, after whatever was negated here.

        The queue holds both lines at once: the Wu this duelist played, and the mirrors landed on
        them. A negation removes one of the two, so what is left is what scores.
        """
        cards = self.queue
        if self.offence_negated:
            cards = [card for card in cards if is_one_of(card, self.suffered)]
        if self.defence_negated:
            cards = excluding(cards, self.suffered)
        if self.boost_negated:  # a Star Hanabi: the boost's stats no longer reach the score
            cards = [card for card in cards if not is_boost_slot(card.power)]
        return cards


@dataclass
class Round:
    """One battle: both duelists field their Wu, and the ground is scored once.

    A stat challenge is a single battle fought with the whole wager, laid down together. A
    tournament is three battles of one Wu, and ``stat`` is what changes between them.
    """

    stat: str = ""  # the stat this battle contests — the whole challenge, or one leg of a tournament
    player: Side = field(default_factory=Side)
    bot: Side = field(default_factory=Side)
    # Wu each side has laid down here (boosts ride along, they do not count). Split rather than one
    # shared count so a duelist can be asked for a different number than their opponent — symmetric
    # (the two always match) for every showdown except Jack-bots Attack!, the one place a duelist may
    # wager zero while the other still owes.
    player_fielded: int = 0
    bot_fielded: int = 0
    score: int = 0  # from the player's side: +2 the contested stat, +1 each other
    winner: bool | None = None  # True player, False bot, None a dead heat
    # A Heart of Jong boosted here summons a separate fighter; the side that did NOT boost it may field one
    # extra OFF-WAGER Wu to answer (it scores but is never staked). This records who boosted it.
    heart_summoner: bool | None = None
    # An Emperor Scorpion fielded against Mala Mala Jong wins this battle outright — the side it hands
    # the leg to, overriding the score (see logic/jong.py; the whole showdown still needs the rounds).
    bane_winner: bool | None = None

    def sides(self, is_player: bool) -> tuple[Side, Side]:
        """``(mine, theirs)`` — where "which duelist" becomes "which half"."""
        return (self.player, self.bot) if is_player else (self.bot, self.player)


@dataclass
class Duelist:
    """One duelist's stake in the showdown: what they brought, and what they can no longer take back."""

    initiative: int = 0
    stakes: list[Card] = field(default_factory=list)  # Wu fielded — the loser forfeits every one
    # A boost Wu is spent once a showdown, not once a battle: you choose which Wu to lift.
    boosts_spent: list[Card] = field(default_factory=list)
    # An off-wager balance Wu (answering a boosted Heart of Jong): it scores and it WEARS like any Wu,
    # but it is never staked — it cannot be lost, only worn out after three showdowns and deposited.
    off_wager: list[Card] = field(default_factory=list)


@dataclass(frozen=True)
class Ground:
    """The terms a battle is fought under: everything a score depends on but the Wu themselves."""

    stats: Sequence[str]  # the stat columns, in the order the card prints them
    background: str
    player_stats: Mapping[str, int]
    bot_stats: Mapping[str, int]
    bonus_cancelled: bool = False  # a Serpent's Tail is on the table — nothing resonates
    bonus_reversed: bool = False  # a Celestial Dial is on the table — resonance and opposition swap
    # Hannibal's Elemental Deflection, both halves — the elements only, never metal. Empty otherwise.
    #   bot_ward: his OWN Wu ignore the arena's drag (−1 -> 0), keeping the lift — a ward on his side.
    #   player_deflect: the foe's arena LIFT (+1 -> 0) is turned aside — the attacking half.
    bot_ward: frozenset[str] = frozenset()
    player_deflect: frozenset[str] = frozenset()
    # Who holds priority. The last word on a battle nothing else can separate — the same rule the
    # showdown itself ends on, so a duelist who sets the terms holds the ground at every level.
    challenger_is_player: bool = True


def score_battle(battle: Round, ground: Ground) -> None:
    """Weigh one battle in place. **Points, then initiative.**

    The points: the contested stat counts ×2, the other two count ×1 each. A positive ``score`` means
    the player leads, and the bot plays to make it negative.

    **Level goes to initiative, and so every battle has a winner.** Level is not a corner case — take
    the contested stat, lose the other two, and it is exactly level: +2 −1 −1 = 0. Three battles,
    three winners: a tournament ends 2:1 or 3:0, never a draw.
    """
    battle.player.result.clear()
    battle.bot.result.clear()
    score = 0
    for stat in ground.stats:
        elemental_bonus, point = (1, 2) if stat == battle.stat else (0, 1)
        if ground.bonus_cancelled:
            elemental_bonus = 0
        elif ground.bonus_reversed:
            elemental_bonus = -elemental_bonus  # resonance now costs, opposition now pays
        player_end = end_stat(
            stat, elemental_bonus, battle.player, ground.player_stats, ground.background,
            deflect_lift=ground.player_deflect,
        )
        bot_end = end_stat(
            stat, elemental_bonus, battle.bot, ground.bot_stats, ground.background,
            also_ward=ground.bot_ward,
        )
        battle.player.result.append(player_end)
        battle.bot.result.append(bot_end)
        score += 0 if player_end == bot_end else point if player_end > bot_end else -point

    battle.score = score
    battle.winner = score > 0 if score else ground.challenger_is_player


def score_brawl(battle: Round, ground: Ground) -> None:
    """Weigh a Jack-bots Attack! battle in place — a **Brawl**, not a contested-stat duel.

    No stat is named, so none is weighted: all three carry the arena's swing equally (nothing is
    singled out as "the challenge" to gate it to), and the winner is whoever leads more of the three
    individual comparisons — **2 of 3**, not the summed margin ``score_battle`` reads. A stalemate —
    the count itself ties, e.g. 1-1 with one draw — goes to the challenger, the same tiebreak an
    ordinary level battle already uses.
    """
    battle.player.result.clear()
    battle.bot.result.clear()
    won = 0  # positive: the player leads more stats; negative: the bot does
    for stat in ground.stats:
        elemental_bonus = 1
        if ground.bonus_cancelled:
            elemental_bonus = 0
        elif ground.bonus_reversed:
            elemental_bonus = -elemental_bonus
        player_end = end_stat(
            stat, elemental_bonus, battle.player, ground.player_stats, ground.background,
            deflect_lift=ground.player_deflect,
        )
        bot_end = end_stat(
            stat, elemental_bonus, battle.bot, ground.bot_stats, ground.background,
            also_ward=ground.bot_ward,
        )
        battle.player.result.append(player_end)
        battle.bot.result.append(bot_end)
        won += 0 if player_end == bot_end else (1 if player_end > bot_end else -1)

    battle.score = won
    battle.winner = won > 0 if won else ground.challenger_is_player


def end_stat(
    stat: str,
    elemental_bonus: int,
    side: Side,
    character: Mapping[str, int],
    background: str,
    also_ward: Collection[str] = (),
    deflect_lift: Collection[str] = (),
) -> int:
    """One duelist's final value for one stat: their own, their Wu, and what was done to them.

    Each of those three can be negated out from under them for the battle — see ``Side``. A trapped
    duelist brings no character; a disarmed one brings no Wu; a warded one carries no curse.
    """
    base = {name: 0 for name in character} if side.base_negated else character
    return count_end_stats(
        stat,
        elemental_bonus,
        side.counted(),
        base,
        background,
        earns_bonus=side.contributors(),
        suffers_bonus=side.curses(),
        element_as=side.element_as,
        ward=side.ward | set(also_ward),
        deflect_lift=deflect_lift,
        shielded=stat in side.shielded,
    )
