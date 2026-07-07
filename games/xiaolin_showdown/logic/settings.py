"""``XiaolinSettings`` — the game's tunable settings, a typed view over the engine ``Settings``.

These rule constants are player-editable on the Settings screen and frozen into each save (the
engine persists settings in the save state). The engine
owns *how* settings are stored and modified; the game owns *which* knobs exist and their
defaults. ``FIRST_DECK_CARD`` stays a structural constant — tied to the card-data layout, not a
player choice.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any

from termcade.core.settings import Settings


@dataclass(frozen=True)
class XiaolinSettings:
    max_hand_size: int = 6
    starting_hand_player: int = 5
    starting_hand_bot: int = 5
    max_deck_size: int = 20
    point_limit: int = 13
    starting_points_player: int = 0
    starting_points_bot: int = 0
    draw_limit: int = 1
    deposit_limit: int = 1
    empty_draw_limit: int = 3

    @classmethod
    def from_settings(cls, settings: Settings) -> "XiaolinSettings":
        """Read the values out of an engine ``Settings``' ``options`` (defaults fill any gaps)."""
        merged: dict[str, Any] = {**asdict(cls()), **settings.options}
        return cls(**{f.name: int(merged[f.name]) for f in fields(cls)})

    def to_settings(self, settings: Settings | None = None) -> Settings:
        """Write these values into an engine ``Settings``' ``options`` (keeps other options)."""
        base = settings or Settings()
        return Settings(difficulty=base.difficulty, options={**base.options, **asdict(self)})


def default_settings() -> Settings:
    """The game's shipped defaults — the starting point for the Settings screen."""
    return XiaolinSettings().to_settings()
