"""What a battle is, and how it is weighed.

Pure and free of the stage machine, so :mod:`.bot` can reach it: the duel scores a battle to find
who won, the bot scores a hypothetical one to find what to play, and there is one scorer for both.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from .mechanics.cards import excluding
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
    result: list[int] = field(default_factory=list)  # per-stat end values

    def contributors(self) -> list[Card]:
        """The Wu *this* duelist played that still contribute — all the background rewards.

        A curse mirror in the queue is the opponent's Wu. It reads the background too, but against
        this side — see ``suffers_bonus`` in :func:`~.mechanics.scoring.count_end_stats`.
        """
        return contributing(excluding(self.queue, self.suffered))


@dataclass
class Round:
    """One battle: both duelists field their Wu, and the ground is scored once.

    A stat challenge is a single battle fought with the whole wager, laid down together. A
    tournament is three battles of one Wu, and ``stat`` is what changes between them.
    """

    stat: str = ""  # the stat this battle contests — the whole challenge, or one leg of a tournament
    player: Side = field(default_factory=Side)
    bot: Side = field(default_factory=Side)
    fielded: int = 0  # Wu each duelist has laid down here (boosts ride along, they do not count)
    score: int = 0  # from the player's side: +2 the contested stat, +1 each other
    winner: bool | None = None  # True player, False bot, None a dead heat

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


def score_battle(
    battle: Round,
    stats: Sequence[str],
    background: str,
    player_stats: Mapping[str, int],
    bot_stats: Mapping[str, int],
    *,
    bonus_cancelled: bool = False,
) -> None:
    """Weigh one battle in place: its contested stat counts double, the other two count once.

    A positive ``score`` means the player leads. The bot plays to make it negative.
    """
    battle.player.result.clear()
    battle.bot.result.clear()
    score = 0
    for stat in stats:
        elemental_bonus, point = (1, 2) if stat == battle.stat else (0, 1)
        if bonus_cancelled:  # a Serpent's Tail is on the table — nothing resonates
            elemental_bonus = 0
        player_end = end_stat(stat, elemental_bonus, battle.player, player_stats, background)
        bot_end = end_stat(stat, elemental_bonus, battle.bot, bot_stats, background)
        battle.player.result.append(player_end)
        battle.bot.result.append(bot_end)
        score += 0 if player_end == bot_end else point if player_end > bot_end else -point

    battle.score = score
    battle.winner = None if score == 0 else score > 0


def end_stat(
    stat: str,
    elemental_bonus: int,
    side: Side,
    character: Mapping[str, int],
    background: str,
) -> int:
    """One duelist's final value for one stat: their own, their Wu, and what was done to them."""
    return count_end_stats(
        stat,
        elemental_bonus,
        side.queue,
        character,
        background,
        earns_bonus=side.contributors(),
        suffers_bonus=contributing(side.suffered),
    )
