"""The boss ladder — bosses are earned by winning, not chosen off a menu from the start.

Beating Hard opens the boss tier at its easiest chair (Jack); beating each boss in turn opens the
next. Ordered by MECHANIC, not character id — ``_BOSS_ARCHETYPE`` in
``screens/character_select.py`` already keys the boss picker off it, and a mechanic survives a DB
renumber that a hardcoded id would not.
"""

from __future__ import annotations

from dataclasses import replace

from termcade.core.settings import Difficulty, Settings

from ..mechanics.powers import Mechanic, mechanic_of
from ..schema.models import Character

# Jack first — Hard's own reward — then the boss tier's own ladder, Hannibal < Wuya < Chase (the
# order BALANCE.md measures them in).
LADDER: tuple[Mechanic, ...] = (
    Mechanic.BOT,
    Mechanic.MORPH,
    Mechanic.WITCHCRAFT,
    Mechanic.BEAST_FORM,
)

# Where the cleared count lives in Settings.options — bookkeeping, not a preference (see
# ``game.py``'s ``private_options``), so it survives the settings prune and is never shipped in
# the defaults.
LADDER_OPTION = "boss_ladder"


def progress(settings: Settings) -> int:
    """How many ladder stages are cleared. 0 means Hard itself is still unbeaten."""
    return int(settings.options.get(LADDER_OPTION, 0))


def boss_tier_unlocked(settings: Settings) -> bool:
    return progress(settings) > 0


def effective_difficulty(settings: Settings) -> Difficulty:
    """The difficulty a NEW run actually plays at — BOSS folds to HARD until the ladder has opened
    it, the same way a stale NORMAL folds to Easy (see ``settings.roster_of``).

    Guards a settings file written before the ladder existed (or hand-edited): without this, a
    saved ``difficulty: boss`` with no ladder progress would send a player straight to an empty
    boss picker instead of the tier they last actually earned.
    """
    if settings.difficulty is Difficulty.BOSS and not boss_tier_unlocked(settings):
        return Difficulty.HARD
    return settings.difficulty


def unlocked_bosses(bosses: list[Character], settings: Settings) -> list[Character]:
    """The boss roster cut down to what the ladder has opened, in ladder order."""
    by_mechanic = {mechanic_of(boss.power): boss for boss in bosses}
    return [by_mechanic[m] for m in LADDER[: progress(settings)] if m in by_mechanic]


def record_win(settings: Settings, *, difficulty: Difficulty, boss: Character | None) -> Settings:
    """Advance the ladder off a player win. Returns ``settings`` itself when nothing advances.

    A stage only advances when the win lands exactly at the ladder's current edge — replaying an
    already-cleared boss (or Easy) does nothing, and a boss reached out of order (should not
    happen; the picker only ever offers unlocked ones) cannot skip a stage.

    ``progress`` counts CLEARED stages, so the boss actually fightable at ``progress == N`` is
    ``LADDER[N - 1]`` (index ``N - 1``) — beating it is what takes ``progress`` to ``N + 1``.
    """
    current = progress(settings)
    if boss is None:
        advanced = 1 if difficulty is Difficulty.HARD and current < 1 else current
    else:
        mechanic = mechanic_of(boss.power)
        stage = LADDER.index(mechanic) if mechanic in LADDER else -1
        advanced = current + 1 if stage == current - 1 else current
    if advanced == current:
        return settings
    return replace(settings, options={**settings.options, LADDER_OPTION: advanced})
