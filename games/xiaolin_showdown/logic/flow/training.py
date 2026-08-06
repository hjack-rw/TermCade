"""Training — the slow climb toward the stat cap, paid for in lost showdowns and spent turns.

The bar fills two ways: losing a showdown (``settings.loss_fill_player``/``_bot``) and spending a
temple turn training (+1). A full bar (``settings.train_length_player``/``_bot``) pays out: one base
stat of the duelist's
CHOICE rises by one — the player picks theirs, the bot shores up its lowest — and the bar resets to
climb again. It stops only at the wall: no stat ever passes ``settings.stat_cap``, the ceiling the
whole card pool is priced against, and a duelist with every stat at the cap has nothing left to
train.

The same rule binds both duelists, which is exactly what makes it a fair asymmetry for boss runs: a
boss already sits at the cap on every stat — MASTER — while the player can still climb.
"""

from __future__ import annotations

from ..config.settings import XiaolinSettings
from ..schema.catalog import load_mechanic_config
from ..schema.models import Mechanic, Player
from ..schema.state import XiaolinState

_BOT = load_mechanic_config()["bot"]
_TRAIN_BOOST = load_mechanic_config()["train_boost"]

# Boss-run rule: a beating from a boss teaches DOUBLE `settings.loss_fill`. The boss sits at the cap,
# so only the player can collect. See docs/design/BOSSES.md. Not mechanic-tied (applies to any boss),
# so it stays a plain constant rather than a `mechanic_config` row.
_BOSS_LOSS_MULTIPLIER = 2
# Jack's own ceiling on FORCE alone, one below the universal `settings.stat_cap` — agility trains all
# the way to the cap, but force stops short. See docs/design/BOSSES.md.
_JACK_FORCE_MARGIN = _BOT["jack_force_margin"]

# `power.train_step` is calibrated against the shipped `XiaolinSettings.train_length` default (10): a
# third of the bar, two thirds, or the whole thing at once (Agalmatosis, the Sapphire Dragon — the
# strongest summon). Read back as that SHARE of the live setting, not the literal number, so a
# house-ruled bar length keeps each summon's fraction of the bar rather than its old absolute step.
# The tiers (3/6/10, `power.train_step`'s own values) are structural, so they stay the dict's keys;
# each fraction is a `mechanic_config` row under `train_boost`.
_TRAIN_STEP_SHARE: dict[int, tuple[int, int]] = {
    3: (_TRAIN_BOOST["tier1_num"], _TRAIN_BOOST["tier1_den"]),
    6: (_TRAIN_BOOST["tier2_num"], _TRAIN_BOOST["tier2_den"]),
    10: (_TRAIN_BOOST["tier3_num"], _TRAIN_BOOST["tier3_den"]),
}


def train_boost_step(card_train_step: int, settings: XiaolinSettings, *, is_player: bool = True) -> int:
    """How much a summon Wu (TRAIN_BOOST) shoves into the bar at once — ``0`` falls back to the base
    (weakest) tier."""
    numerator, denominator = _TRAIN_STEP_SHARE.get(card_train_step, (1, 3))
    train_length = settings.train_length_player if is_player else settings.train_length_bot
    return (train_length * numerator) // denominator


def doubles_training(player: Player) -> bool:
    """The Ring of Nine Xing, held: every point of training its holder gains counts double."""
    return any(card.power.mechanic is Mechanic.DOUBLE_TRAINING for card in player.whole_hand)


def can_train(player: Player, settings: XiaolinSettings) -> bool:
    """Training is possible while any base stat still has room under the cap."""
    return bool(trainable_stats(player, settings))


def trainable_stats(player: Player, settings: XiaolinSettings) -> list[str]:
    """The stats a payout may raise — every base stat still under the cap. Jack Spicer's force alone
    trains toward `_JACK_FORCE_MARGIN` below the cap rather than the universal one — see its comment.

    Good Jack (a Yin/Yang Yo-Yo away, see `Player.yoyo_flipped`) trains neither: while worn, only
    his own separate intellect can train (see `Player.good_jack_intellect`) — force/agility only
    ever move in Evil Jack form, mirrored onto Good Jack's afterward (`duel.Duel._jack_base`).
    """
    is_jack = player.character.power.mechanic is Mechanic.BOT
    if is_jack and player.yoyo_flipped:
        return ["intellect"] if player.good_jack_intellect < settings.stat_cap else []
    stats = player.character.stats
    jack_force_cap = settings.stat_cap - _JACK_FORCE_MARGIN
    return [
        s for s, v in stats.items()
        if v < (jack_force_cap if is_jack and s == "force" else settings.stat_cap)
    ]


def payout_ready(player: Player, settings: XiaolinSettings, *, is_player: bool = True) -> bool:
    """A full bar is waiting for its holder to pick the stat it raises."""
    train_length = settings.train_length_player if is_player else settings.train_length_bot
    return (
        player.training >= train_length
        and not player.just_trained
        and can_train(player, settings)
    )


def add_progress(
    player: Player, settings: XiaolinSettings, amount: int = 1, *, is_player: bool = True
) -> bool:
    """Fill the bar by ``amount``. Returns whether a payout is now waiting.

    A duelist who cannot train (every stat at the cap) never accrues progress — a boss's bar stays
    empty rather than filling toward a payout it can never take. A just-taken payout blocks the
    climb too, until the turnover resets the bar (see :func:`turn_over`).
    """
    if player.just_trained or not can_train(player, settings):
        return False
    train_length = settings.train_length_player if is_player else settings.train_length_bot
    player.training = min(player.training + amount, train_length)
    return payout_ready(player, settings, is_player=is_player)


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


def pick_stat(player: Player, settings: XiaolinSettings) -> str:
    """The BOT's payout policy: shore up the weakness — its lowest stat with room."""
    stats = player.character.stats
    return min(trainable_stats(player, settings), key=lambda s: stats[s])


def boss_loss_fill(settings: XiaolinSettings, *, is_player: bool = True) -> int:
    """What a boss's beating teaches: double the ordinary ``loss_fill``."""
    loss_fill = settings.loss_fill_player if is_player else settings.loss_fill_bot
    return _BOSS_LOSS_MULTIPLIER * loss_fill


def record_showdown(state: XiaolinState, settings: XiaolinSettings, *, player_won: bool) -> str | None:
    """A finished showdown teaches its LOSER: their bar gains ``settings.loss_fill`` — double, when a
    boss is doing the teaching, the whole bar at once for Jack Spicer alone (see `_JACK...` note
    below). The winner was paid in Wu.

    The bot cashes a full bar on the spot (see :func:`pick_stat`) and the raised stat's name is
    returned, for the log. The player's payout waits instead — the temple offers them the choice.
    """
    loser = state.bot if player_won else state.player
    loser_is_player = not player_won
    is_jack = state.boss_run and loser is state.bot and loser.character.power.mechanic is Mechanic.BOT
    if is_jack:
        # One defeat teaches him the whole lesson, an instant payout rather than a partial fill.
        fill = settings.train_length_bot
    else:
        loss_fill = settings.loss_fill_player if loser_is_player else settings.loss_fill_bot
        fill = boss_loss_fill(settings, is_player=loser_is_player) if state.boss_run else loss_fill
    if doubles_training(loser):  # a Ring of Nine Xing still in hand after the showdown doubles the lesson
        fill *= 2
    if add_progress(loser, settings, fill, is_player=loser_is_player) and loser is state.bot:
        stat = pick_stat(loser, settings)
        raise_stat(loser, stat)
        return stat
    return None
