"""Chase Young's own Beast Form call — the rest of it lives in the shared mechanic table
(``mechanics.powers.Mechanic.BEAST_FORM``), which every boss's temple/duel AI shares the file with.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..schema.catalog import load_mechanic_config
from ..schema.models import Mechanic, Player

# Chase's one counter — a Sphere of Jianyu negates his character entirely, the whole Beast Form
# threat with it.
counter = frozenset({Mechanic.NULLIFY_STATS})


# Chase Young activates Beast Form only when a contested stat is close — his lead on it is under
# `duel.BEAST_BOOST`, so the boost could decide the battle. Ahead by more he stays an ordinary
# duelist: his Wu score, and a win GIFTS the prize to the duelist he beat.
BEAST_MARGIN = load_mechanic_config()["beast_form"]["margin"]


def choose_beast_form(chase: Player, opponent: Player, stats: Sequence[str]) -> str | None:
    """Chase's per-showdown call: which contested stat to spend Beast Form on, or ``None``.

    Beast Form is `duel.BEAST_BOOST` on ONE stat, once a fight, and it deadens his Wu — they are
    wagered, never wielded. It does NOT cost him the prize: the beast KEEPS what it wins, and it is
    the ordinary Wu-play win that gifts the prize away (see the duel's `_award_prize`).

    He spends it where a battle is close: the tightest contested stat, where his base lead over the
    opponent's reach is under the margin. Ahead by more on all of them, he fields his Wu like anyone
    else — and gifts the prize if he wins.

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
