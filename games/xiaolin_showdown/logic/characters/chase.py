"""Chase Young's own Beast Form call — the rest of it lives in the shared mechanic table
(``mechanics.powers.Mechanic.BEAST_FORM``), which every boss's temple/duel AI shares the file with.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..schema.models import Mechanic, Player

# Chase's one counter — a Sphere of Jianyu negates his character entirely, the whole Beast Form
# threat with it.
counter = frozenset({Mechanic.NULLIFY_STATS})


# Chase Young activates Beast Form only when a contested stat is close — his lead on it is under
# `duel.BEAST_BOOST`, so the boost could decide the battle. Ahead by more he stays an ordinary
# duelist: his Wu score, and a win GIFTS the prize to the duelist he beat. Swept from the harness
# (XS_BEAST_MARGIN).
#
# Since the beast KEEPS its prize (see the duel's `_award_prize`), beasting more makes him STRONGER,
# monotonically: 0 (never) 5.5% player win, 2 -> 3.2%, 4 -> 2.5%, always -> 2.0% (n=600). Sweeps
# taken before the prize flip read this slope the other way round.
#
# Three, paired with a BEAST_BOOST of 1: the pair reads 7.1% player win and the beast fires on 61%
# of his showdowns, so the mode is a real choice rather than a rule. At boost 2 the curve was crushed
# flat and every route to this win rate meant a Chase who barely beasts at all.
BEAST_MARGIN = 3


def choose_beast_form(chase: Player, opponent: Player, stats: Sequence[str]) -> str | None:
    """Chase's per-showdown call: which contested stat to spend Beast Form on, or ``None``.

    Beast Form is `duel.BEAST_BOOST` on ONE stat, once a fight, and it deadens his Wu — they are
    wagered, never wielded. What it does NOT cost him is the prize: the beast KEEPS what it wins,
    and it is the ordinary Wu-play win that gifts the prize away (see the duel's `_award_prize`).
    That is why beasting more makes him stronger, and why the margin below is the whole choice.

    So he spends it where a battle is close: the tightest contested stat, where his base lead over
    the opponent's reach is under the margin. Ahead by more on all of them, he fields his Wu like
    anyone else — and gifts the prize if he wins.

    ``stats`` is the contested set — one stat for a challenge, all three for a tournament (he may
    still boost only one).
    """
    def lead(stat: str) -> int:
        reach = opponent.character.stats[stat] + max(
            (card.stats[stat] or 0 for card in opponent.hand), default=0
        )
        return chase.character.stats[stat] - reach

    tightest = min(stats, key=lead)
    return tightest if lead(tightest) < BEAST_MARGIN else None
