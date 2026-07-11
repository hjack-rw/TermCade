"""``XiaolinSettings`` — the game's tunable settings, a typed view over the engine ``Settings``.

These rule constants are player-editable on the Settings screen and frozen into each save (the
engine persists settings in the save state). The engine
owns *how* settings are stored and modified; the game owns *which* knobs exist and their
defaults. ``FIRST_DECK_CARD`` stays a structural constant — tied to the card-data layout, not a
player choice.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, fields
from typing import Any

from termcade.core.settings import Difficulty, Settings

from .constants import FIRST_DECK_CARD
from .models import Card

# A duelist wins by banking this share of every point on the table. Kept as a *share* so the target
# grows with the card pool — a hardcoded number would quietly get easier every time a Wu is added.
POINT_SHARE = 0.4


@dataclass(frozen=True)
class XiaolinSettings:
    max_hand_size: int = 6
    starting_hand_player: int = 5
    starting_hand_bot: int = 5
    max_deck_size: int = 20
    point_limit: int = 14  # the shipped default; `default_settings` recomputes it from the cards
    starting_points_player: int = 0
    starting_points_bot: int = 0
    draw_limit: int = 1
    deposit_limit: int = 1
    empty_draw_limit: int = 3
    # The prize Wu is only claimed if the winner's Challenge stat clears this. It is the one number
    # that decides whether Wu circulate or the pile just drains — measured, the prize moves in about
    # one showdown in six. Tunable rather than derived: it turns on character stats AND card stats
    # together, and that relationship is not something we can compute yet.
    prize_threshold: int = 7
    max_wager: int = 3  # the most Wu either duelist may be made to stake in one showdown

    def __post_init__(self) -> None:
        """Clamp player-entered values to a playable range, so an edited Settings screen can never
        deal a broken game (e.g. a deck smaller than the two hands, or a zero-card hand)."""
        clamp = object.__setattr__  # the dataclass is frozen; this is the sanctioned way to write
        clamp(self, "point_limit", max(2, self.point_limit))
        for hand in ("max_hand_size", "starting_hand_player", "starting_hand_bot"):
            clamp(self, hand, max(1, getattr(self, hand)))
        # a hand is dealt to its full starting size, so its cap can't sit below either starting hand
        clamp(
            self,
            "max_hand_size",
            max(self.max_hand_size, self.starting_hand_player, self.starting_hand_bot),
        )
        clamp(self, "prize_threshold", max(0, self.prize_threshold))
        clamp(self, "max_wager", max(1, self.max_wager))
        for limit in ("draw_limit", "deposit_limit", "empty_draw_limit"):
            clamp(self, limit, max(1, getattr(self, limit)))
        for points in ("starting_points_player", "starting_points_bot"):
            clamp(self, points, max(0, min(getattr(self, points), self.point_limit - 1)))
        min_deck = self.starting_hand_player + self.starting_hand_bot + 1
        clamp(self, "max_deck_size", max(self.max_deck_size, min_deck))

    @classmethod
    def from_settings(cls, settings: Settings) -> "XiaolinSettings":
        """Read the values out of an engine ``Settings``' ``options`` (defaults fill any gaps)."""
        merged: dict[str, Any] = {**asdict(cls()), **settings.options}
        return cls(**{f.name: int(merged[f.name]) for f in fields(cls)})

    def to_settings(self, settings: Settings | None = None) -> Settings:
        """Write these values into an engine ``Settings``' ``options`` (keeps other options)."""
        base = settings or Settings()
        return Settings(difficulty=base.difficulty, options={**base.options, **asdict(self)})

    @classmethod
    def coerce(
        cls, values: Mapping[str, int]
    ) -> tuple["XiaolinSettings", dict[str, tuple[int, int]]]:
        """Build settings from raw entered ints, clamping to a playable range. Returns the clamped
        instance plus a report ``{field: (entered, clamped)}`` naming every value the clamp had to
        change — empty when the input was already valid. Lets the UI reject/flag out-of-range input
        instead of silently accepting a value that does nothing."""
        coerced = cls(**dict(values))
        adjusted = {
            name: (values[name], getattr(coerced, name))
            for name in values
            if values[name] != getattr(coerced, name)
        }
        return coerced, adjusted


def is_hard(difficulty: Difficulty) -> bool:
    """The game runs two tiers, not three: only HARD is the hard tier.

    Picks the opponent roster (``Catalog.opponents``) and the bot's deposit skill alike, so the two
    can never disagree. Folds a stale ``NORMAL`` (an older settings file, or the engine default)
    into Easy.
    """
    return difficulty is Difficulty.HARD


def point_limit_for(cards: Iterable[Card]) -> int:
    """How many points win the run — a share of every point in the draw pool.

    Derived, not hardcoded: the pool only ever grows, and a fixed target would quietly get easier
    with every Wu added. The player can still override it on the Settings screen; this is only what
    the game ships with.
    """
    total = sum(card.points for card in cards if card.id >= FIRST_DECK_CARD)
    return max(2, round(total * POINT_SHARE))


def default_settings() -> Settings:
    """The game's shipped defaults — the starting point for the Settings screen.

    XS runs two tiers, Easy and Hard, so it pins the difficulty rather than inheriting the engine's
    three-valued ``NORMAL`` default — the Settings screen would otherwise offer two states while a
    third sat unreachable behind them. ``turn.is_hard`` still folds any stale ``NORMAL`` into Easy.
    """
    from .catalog import load_catalog  # local: settings must not drag the DB into every import

    defaults = XiaolinSettings(point_limit=point_limit_for(load_catalog().cards))
    return defaults.to_settings(Settings(difficulty=Difficulty.EASY))
