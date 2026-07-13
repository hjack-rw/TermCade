"""Persisted settings: difficulty + free-form game options.

``from_dict`` merges a loaded file over game-supplied defaults, so adding a new option in a later
version never breaks an old settings file.

The merge is forward-compatible; it is not *backward*-compatible on its own, and that is what
``ENGINE_OPTIONS`` and the prune in :meth:`SettingsStore.load` are for. A key the game has since
removed lives on in the file forever — Xiaolin's settings still carried ``draw_limit`` and
``deposit_limit`` long after the one-action economy replaced both. They did nothing, which is worse
than doing something wrong: the next person to read the file believes them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class Difficulty(StrEnum):
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"


@dataclass
class Settings:
    difficulty: Difficulty = Difficulty.NORMAL
    options: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"difficulty": str(self.difficulty), "options": self.options}

    @classmethod
    def from_dict(cls, data: dict[str, Any], defaults: "Settings") -> "Settings":
        difficulty = Difficulty(data.get("difficulty", str(defaults.difficulty)))
        options = {**defaults.options, **data.get("options", {})}
        return cls(difficulty=difficulty, options=options)


# Options the ENGINE owns, in every game. They are not in a cartridge's declared defaults — the app
# writes them itself — so the prune below has to know they are real, or muting the music would delete
# the setting that muted it.
ENGINE_OPTIONS = frozenset({"music", "sfx"})


class SettingsStore:
    """Load/save :class:`Settings` as ``<data_dir>/settings.json``."""

    def __init__(
        self, path: Path, defaults: Settings, *, private_options: frozenset[str] = frozenset()
    ) -> None:
        self._path = path
        self._defaults = defaults
        # Keys the GAME keeps for itself — bookkeeping rather than preferences, so they are absent
        # from the declared defaults on purpose and would otherwise be pruned on sight. Xiaolin's
        # card-pool fingerprint is one: shipped in the defaults it would be inherited by every stale
        # file and defeat the check it exists for.
        self._private = private_options
        self._current: Settings | None = None

    def load(self) -> Settings:
        if self._path.exists():
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._current = self._pruned(Settings.from_dict(data, self._defaults))
        else:
            self._current = Settings(
                difficulty=self._defaults.difficulty,
                options=dict(self._defaults.options),
            )
        return self._current

    def _pruned(self, settings: Settings) -> Settings:
        """Drop options no game and no engine declares — a knob that was removed is not a setting.

        A settings file keeps every key ever written into it. Xiaolin's still carried ``draw_limit``
        and ``deposit_limit`` months after the one-action economy replaced them both: inert, and a trap
        for the next person to read the file and assume they mean something.

        **A game that declares no options at all is opting out**, and keeps whatever it wrote. Options
        are free-form by contract; pruning is a service to a game that has told the engine what its
        options *are*, not a rule imposed on one that has not.
        """
        if not self._defaults.options:
            return settings

        declared = set(self._defaults.options) | ENGINE_OPTIONS | self._private
        kept = {name: value for name, value in settings.options.items() if name in declared}
        if len(kept) == len(settings.options):
            return settings
        return Settings(difficulty=settings.difficulty, options=kept)

    def save(self, settings: Settings | None = None) -> None:
        if settings is not None:
            self._current = settings
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self.current.to_dict(), indent=2), encoding="utf-8")

    @property
    def current(self) -> Settings:
        if self._current is None:
            self.load()
        assert self._current is not None
        return self._current
