"""Who takes the revealed Wu — the four ways to claim it, tried in order, and what happens when
nobody does. See docs/xs_game/CIRCULATION.md for the full rationale.

1. **a decisive blow** — one stat at or above ``N``
2. **a broad win** — two stats at ``N-1``
3. **total command** — all three at ``N-2``
4. **being in tune with the arena** — your Wu belonged where the fight happened

The first three are read off a *single battle*'s three end values, so a tournament (three battles)
gets three bites at them and a stat challenge one.

The fourth asks whether the Wu you fielded belonged in the arena you fought in — resonant Wu count
for you, opposed ones against (and metal is opposed to every coloured ground). A Serpent's Tail
**vetoes** it: if the ground has stopped resonating, nobody was in tune with anything.

Fail all four and the Wu is **lost** — not destroyed. It goes out of play, and it can surface again.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from .battle_types import RoundLike
from .scoring import element_score


class PrizeRoute(StrEnum):
    """How the Wu was claimed. The value is what a player is told."""

    DECISIVE_BLOW = "a decisive blow"
    BROAD_WIN = "a win on two fronts"
    TOTAL_COMMAND = "total command"
    IN_TUNE = "being in tune with the arena"
    # Jack-bots Attack! alone: winning the Brawl claims the Wu outright, no ladder — set directly by
    # `duel.Duel._award_prize`, never returned by `claim_route`.
    BRAWL_WON = "winning the Brawl outright"


def claim_route(
    rounds: Sequence[RoundLike],
    *,
    winner_is_player: bool,
    background: str,
    threshold: int,
    bonus_cancelled: bool = False,
) -> PrizeRoute | None:
    """Which route claims the Wu for the winner, or ``None`` — the Wu is lost.

    ``threshold`` is ``settings.prize_threshold``: the bar a *decisive* blow must clear, so the blow
    itself must reach ``threshold + 1``. The broader routes step down from there.
    """
    bar = threshold + 1

    for battle in rounds:
        end_values = battle.sides(winner_is_player)[0].result
        if not end_values:
            continue  # a battle that never scored — nothing to read
        if max(end_values) >= bar:
            return PrizeRoute.DECISIVE_BLOW
        if sum(value >= bar - 1 for value in end_values) >= 2:
            return PrizeRoute.BROAD_WIN
        if sum(value >= bar - 2 for value in end_values) >= 3:
            return PrizeRoute.TOTAL_COMMAND

    if not bonus_cancelled and _elemental_surplus(rounds, winner_is_player, background) > 0:
        return PrizeRoute.IN_TUNE

    return None


def _elemental_surplus(rounds: Sequence[RoundLike], winner_is_player: bool, background: str) -> int:
    """How far the winner's Wu belonged on the ground they fought on, across the whole showdown.

    +1 for a Wu of the ground's element, −1 for its opposite — and −1 for metal on any coloured
    ground, which is the price metal pays for being at home everywhere and favoured almost nowhere.

    **Every Wu the duelist FIELDED counts.** Being in tune asks what you *brought* to the ground, not
    what it did once it got there, and there are two ways to get a Wu wrong here:

    * A Wu that moves no stat is still standing in the arena. A negation prints 0/0/0, and it is still
      a lump of metal in a water canal — so it counts toward being in tune, stats or no stats.
    * **A curse you cast is a Wu you played**, even though it prints on the *opponent's* Defensive
      line — that is where it lands, not who brought it. Your own copy is spent to zero, so the Wu is
      absent from your Offensive line entirely, and reading only your own side loses it.

    So: your Offensive line, plus their Defensive line. Which, between the two of them, is every Wu you
    put on the table.
    """
    total = 0
    for battle in rounds:
        mine, theirs = battle.sides(winner_is_player)
        # `mine()` drops the spent copies of the curses I cast; `theirs.suffered` is where those curses
        # actually are. Together they are each Wu once — never twice.
        for card in [*mine.mine(), *theirs.suffered]:
            total += element_score(card.element, background)
    return total
