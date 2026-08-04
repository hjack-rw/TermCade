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

from ..schema.models import Mechanic, Player
from ..schema.state import XiaolinState

TRAIN_LENGTH = 10  # what a full bar takes; the temple tooltip reads progress/TRAIN_LENGTH
STAT_CAP = 5  # no base stat may pass this
LOSS_FILL = 1  # what a lost showdown teaches
TRAIN_BOOST_STEP = 3  # a summon Wu spent at the temple (TRAIN_BOOST) shoves this much into the bar at once
# Boss-run rule: a beating from a boss teaches DOUBLE. The boss sits at the cap, so only the player
# can collect. See docs/design/BOSSES.md.
BOSS_LOSS_FILL = 2
# Jack Spicer alone: force/agility (3/3) sit under the cap for him, unlike the other three (already
# MASTER on every stat), so he is the only boss who can bank a loss into a raise. Equal to
# TRAIN_LENGTH: one defeat teaches him the whole lesson, an instant payout rather than a partial
# fill. See docs/design/BOSSES.md.
JACK_LOSS_FILL = TRAIN_LENGTH
# Jack's own ceiling on FORCE alone, below the universal STAT_CAP — agility trains all the way to
# STAT_CAP, but force stops short. See docs/design/BOSSES.md.
JACK_FORCE_CAP = 4


def doubles_training(player: Player) -> bool:
    """The Ring of Nine Xing, held: every point of training its holder gains counts double."""
    return any(card.power.mechanic is Mechanic.DOUBLE_TRAINING for card in player.whole_hand)


def can_train(player: Player) -> bool:
    """Training is possible while any base stat still has room under the cap."""
    return bool(trainable_stats(player))


def trainable_stats(player: Player) -> list[str]:
    """The stats a payout may raise — every base stat still under the cap. Jack Spicer's force alone
    trains toward `JACK_FORCE_CAP` rather than the universal `STAT_CAP` — see its comment.

    Good Jack (a Yin/Yang Yo-Yo away, see `Player.yoyo_flipped`) trains neither: while worn, only
    his own separate intellect can train (see `Player.good_jack_intellect`) — force/agility only
    ever move in Evil Jack form, mirrored onto Good Jack's afterward (`duel.Duel._jack_base`).
    """
    is_jack = player.character.power.mechanic is Mechanic.BOT
    if is_jack and player.yoyo_flipped:
        return ["intellect"] if player.good_jack_intellect < STAT_CAP else []
    stats = player.character.stats
    return [
        s for s, v in stats.items() if v < (JACK_FORCE_CAP if is_jack and s == "force" else STAT_CAP)
    ]


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
    the turnover resets it to climb again (see :func:`turn_over`).

    Good Jack's intellect gain also raises Evil Jack's real one, permanently — training banks onto
    the shared duelist no matter which form earned it (see `trainable_stats`)."""
    is_jack = player.character.power.mechanic is Mechanic.BOT
    if is_jack and player.yoyo_flipped:
        player.good_jack_intellect += 1
        player.character.stats["intellect"] += 1
    else:
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
    teaching, more still for Jack Spicer alone (see :data:`JACK_LOSS_FILL`). The winner was paid in
    Wu.

    The bot cashes a full bar on the spot (see :func:`pick_stat`) and the raised stat's name is
    returned, for the log. The player's payout waits instead — the temple offers them the choice.
    """
    loser = state.bot if player_won else state.player
    is_jack = state.boss_run and loser is state.bot and loser.character.power.mechanic is Mechanic.BOT
    if is_jack:
        fill = JACK_LOSS_FILL
    else:
        fill = BOSS_LOSS_FILL if state.boss_run else LOSS_FILL
    if doubles_training(loser):  # a Ring of Nine Xing still in hand after the showdown doubles the lesson
        fill *= 2
    if add_progress(loser, fill) and loser is state.bot:
        stat = pick_stat(loser)
        raise_stat(loser, stat)
        return stat
    return None
