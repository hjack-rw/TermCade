"""Does a loser-weighted training bar compress the game or blow it open?

Nothing here touches the game. It re-plays the balance harness's loop with a TRAINING bar bolted on,
so the only difference between the baseline and a variant is the bar itself.

  - a showdown pays progress: winner +WIN, loser +LOSS
  - a temple turn may be spent TRAINING: +1 progress, and it costs the action (~2.33 points unbanked)
  - a full bar raises one base stat by +1, once per run, capped at CAP
"""

from __future__ import annotations

import asyncio
import statistics
import sys

sys.argv = ["train_sim", "."]  # balance.py reads its repo path off argv
sys.path[:0] = ["engine", "games", "docs/balance"]

from termcade.core.rng import Rng  # noqa: E402
from termcade.core.settings import Difficulty, Settings  # noqa: E402
from xiaolin_showdown.logic.duel import Duel  # noqa: E402
from xiaolin_showdown.logic.settings import XiaolinSettings, roster_of  # noqa: E402
from xiaolin_showdown.logic.setup import new_game  # noqa: E402
from xiaolin_showdown.logic.turn import bot_turn, refill_hands  # noqa: E402

from balance import CATALOG, competent_choices, player_temple_action  # noqa: E402

CAP = 5  # no base stat may pass this
STATS = ("force", "agility", "intellect")


class Bar:
    """One duelist's training. `spent` is set once the bar has paid out — once a run."""

    def __init__(self, length: int) -> None:
        self.length = length
        self.progress = 0
        self.spent = False

    def can_train(self, player) -> bool:
        """Only worth an action when the bar is unspent and some stat still has room to grow."""
        return not self.spent and any(player.character.stats[s] < CAP for s in STATS)

    def add(self, n: int) -> None:
        if not self.spent:
            self.progress += n

    def full(self) -> bool:
        # `length == 0` is the BASELINE: no bar at all. Without this it reads as instantly full and
        # hands both duelists a free stat — which is what the first run of this actually did.
        return bool(self.length) and not self.spent and self.progress >= self.length

    def cash(self, player) -> str | None:
        """Raise the LOWEST stat with room — shore up the weakness, the obvious line for a policy."""
        if not self.full():
            return None
        options = [s for s in STATS if player.character.stats[s] < CAP]
        if not options:
            self.spent = True
            return None
        stat = min(options, key=lambda s: player.character.stats[s])
        player.character.stats[stat] += 1
        self.spent = True
        return stat


async def play(seed, difficulty, *, length, win, loss, train_on):
    """One run. `length=0` disables training entirely (the baseline)."""
    rng = Rng(seed)
    settings = XiaolinSettings.from_settings(Settings(difficulty=difficulty, options={}))
    state = new_game(CATALOG, rng, CATALOG.character(1), settings=settings,
                     roster=roster_of(difficulty))

    bars = {"player": Bar(length), "bot": Bar(length)}
    trained = {"player": None, "bot": None}
    trainings = {"player": 0, "bot": 0}

    bot_turn(state, settings, rng=rng, difficulty=difficulty)  # the opponent's opening turn
    refill_hands(state, settings, rng=rng)

    showdowns = 0
    while not state.has_ended and showdowns < 60:
        # --- the player's one action: train when the bar is within reach, else play normally
        bar = bars["player"]
        if length and bar.can_train(state.player) and bar.length - bar.progress <= train_on:
            bar.add(1)
            trainings["player"] += 1
            state.actions_taken = settings.actions_per_turn  # training COSTS the turn's action
        else:
            player_temple_action(state, settings, rng, difficulty)
        if state.player.points >= settings.point_limit:
            state.has_ended = True
        if state.has_ended:
            break
        trained["player"] = trained["player"] or bars["player"].cash(state.player)

        duel_ref: list = []
        duel = Duel(state, rng, competent_choices(state, rng, duel_ref), settings)
        duel_ref.append(duel)
        stage, guard = -1, 0
        while stage != 0 and guard < 12:
            stage = await duel.advance()
            guard += 1
        showdowns += 1

        if length:  # a showdown pays both duelists — the loser more
            player_won = bool(duel.duel.winner)
            bars["player"].add(win if player_won else loss)
            bars["bot"].add(loss if player_won else win)

        if state.has_ended:
            break
        refill_hands(state, settings, rng=rng)

        # --- the opponent's turn: same rule, its own bar
        bar = bars["bot"]
        if length and bar.can_train(state.bot) and bar.length - bar.progress <= train_on:
            bar.add(1)
            trainings["bot"] += 1
            state.bot_actions_taken = settings.actions_per_turn
        elif not state.has_ended:
            bot_turn(state, settings, rng=rng, difficulty=difficulty)
        trained["bot"] = trained["bot"] or bars["bot"].cash(state.bot)
        refill_hands(state, settings, rng=rng)

    p = state.player.points + sum(c.points for c in state.player.whole_hand)
    b = state.bot.points + sum(c.points for c in state.bot.whole_hand)
    return {
        "won": p > b,
        "margin": abs(p - b),
        "showdowns": showdowns,
        "player_filled": bars["player"].spent,
        "bot_filled": bars["bot"].spent,
        "trainings": trainings["player"] + trainings["bot"],
    }


async def sweep(runs, **cfg):
    out = {}
    for difficulty in (Difficulty.EASY, Difficulty.HARD, Difficulty.BOSS):
        rows = [await play(seed, difficulty, **cfg) for seed in range(1, runs + 1)]
        out[str(difficulty)] = rows
    return out


async def main():
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    configs = [
        ("baseline (no training)", dict(length=0, win=0, loss=0, train_on=0)),
        ("bar 8  win 0 / loss 1", dict(length=8, win=0, loss=1, train_on=4)),
        ("bar 8  win 0 / loss 2", dict(length=8, win=0, loss=2, train_on=4)),
        ("bar 10 win 0 / loss 1", dict(length=10, win=0, loss=1, train_on=4)),
    ]
    print(f"{runs} runs a tier, competent player both sides, no summons yet\n")
    print(f"{'config':26} {'easy':>7} {'hard':>7} {'boss':>7} {'margin':>7} {'filled':>7} {'trainings':>10}")
    for name, cfg in configs:
        res = await sweep(runs, **cfg)
        easy, hard, boss = res["easy"], res["hard"], res["boss"]
        rows = easy + hard + boss
        wins_e = sum(r["won"] for r in easy) / len(easy)
        wins_h = sum(r["won"] for r in hard) / len(hard)
        wins_b = sum(r["won"] for r in boss) / len(boss)
        margin = statistics.mean(r["margin"] for r in rows)
        filled = sum(r["player_filled"] + r["bot_filled"] for r in rows) / (2 * len(rows))
        trains = statistics.mean(r["trainings"] for r in rows)
        print(f"{name:26} {wins_e:6.1%} {wins_h:6.1%} {wins_b:6.1%} {margin:7.1f} {filled:6.0%} {trains:10.1f}")


asyncio.run(main())
