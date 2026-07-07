"""Persisted settings: difficulty + free-form game options.

``from_dict`` merges a loaded file over game-supplied defaults, so adding a new
option in a later version never breaks an old settings file.
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


class SettingsStore:
    """Load/save :class:`Settings` as ``<data_dir>/settings.json``."""

    def __init__(self, path: Path, defaults: Settings) -> None:
        self._path = path
        self._defaults = defaults
        self._current: Settings | None = None

    def load(self) -> Settings:
        if self._path.exists():
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._current = Settings.from_dict(data, self._defaults)
        else:
            self._current = Settings(
                difficulty=self._defaults.difficulty,
                options=dict(self._defaults.options),
            )
        return self._current

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
