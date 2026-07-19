"""Training — the slow climb toward the stat cap, paid for in lost showdowns and spent turns.

The bar fills two ways: losing a showdown (+1) and spending a temple turn training (+1). A full bar
pays out: one base stat of the duelist's CHOICE rises by one — the player picks theirs, the bot
shores up its lowest — and the bar resets to climb again. It stops only at the wall: no stat ever
passes the cap of 5, the ceiling the whole card pool is priced against, and a duelist with every
stat at the cap has nothing left to train.

The same rule binds both duelists, which is exactly what makes it a fair asymmetry for boss runs: a
boss already sits at the cap on every stat — MASTER — while the player can still climb.
"""

from __future__ import annotations

from .models import Player
from .state import XiaolinState

TRAIN_LENGTH = 10  # what a full bar takes; the temple tooltip reads progress/TRAIN_LENGTH
STAT_CAP = 5  # no base stat may pass this — outstat the plain Wu and the pricing collapses
LOSS_FILL = 1  # what a lost showdown teaches
# Boss-run rule: a beating from a boss teaches DOUBLE. One of the two asymmetries that offset a
# boss's powers without touching duel stats (measured: 0.5% -> 3.0% alone, 5.0% with the extra
# actions — docs/design/BOSSES.md). Written as the same law for both sides; the boss sits at the
# cap, so only the player can collect.
BOSS_LOSS_FILL = 2


def can_train(player: Player) -> bool:
    """Training is possible while any base stat still has room under the cap."""
    return bool(trainable_stats(player))


def trainable_stats(player: Player) -> list[str]:
    """The stats a payout may raise — every base stat still under the cap."""
    return [s for s, v in player.character.stats.items() if v < STAT_CAP]


def payout_ready(player: Player) -> bool:
    """A full bar is waiting for its holder to pick the stat it raises."""
    return player.training >= TRAIN_LENGTH and not player.just_trained and can_train(player)


def add_progress(player: Player, amount: int = 1) -> bool:
    """Fill the bar by ``amount``. Returns whether a payout is now waiting.

    A duelist who cannot train (every stat at the cap) never accrues progress — a boss's bar stays
    empty rather than filling toward a payout it can never take. A just-taken payout blocks the
    climb too, until the turnover resets the bar (see :func:`turn_over`).
    """
    if player.just_trained or not can_train(player):
        return False
    player.training = min(player.training + amount, TRAIN_LENGTH)
    return payout_ready(player)


def raise_stat(player: Player, stat: str) -> None:
    """The payout: the chosen base stat rises by one. The bar stays full for the rest of the turn —
    the turnover resets it to climb again (see :func:`turn_over`)."""
    player.character.stats[stat] += 1
    player.just_trained = True


def turn_over(player: Player) -> None:
    """A new temple turn: a bar whose payout was taken resets to 0 and may climb again."""
    if player.just_trained:
        player.training = 0
        player.just_trained = False


def pick_stat(player: Player) -> str:
    """The BOT's payout policy: shore up the weakness — its lowest stat with room."""
    stats = player.character.stats
    return min(trainable_stats(player), key=lambda s: stats[s])


def record_showdown(state: XiaolinState, *, player_won: bool) -> str | None:
    """A finished showdown teaches its LOSER: their bar gains one — two, when a boss is doing the
    teaching. The winner was paid in Wu.

    The bot cashes a full bar on the spot (see :func:`pick_stat`) and the raised stat's name is
    returned, for the log. The player's payout waits instead — the temple offers them the choice.
    """
    loser = state.bot if player_won else state.player
    fill = BOSS_LOSS_FILL if state.boss_run else LOSS_FILL
    if add_progress(loser, fill) and loser is state.bot:
        stat = pick_stat(loser)
        raise_stat(loser, stat)
        return stat
    return None
