"""``XiaolinSettings`` — the game's tunable settings, a typed view over the engine ``Settings``.

These rule constants are player-editable on the Settings screen and frozen into each save (the
engine persists settings in the save state). The engine
owns *how* settings are stored and modified; the game owns *which* knobs exist and their
defaults. Which cards are even in the pool (``constants.in_pool``) stays a structural fact — tied
to the card-data layout, not a player choice.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, fields
from typing import Any

from termcade.app.game import SaveNote
from termcade.core.settings import Difficulty, Settings

from ..schema.constants import in_pool
from ..schema.models import Card

# A duelist wins by banking this share of the points left in the *pile* — see `point_limit_for`, which
# takes the two opening hands off the top first. Kept as a *share* so the target grows with the pool;
# a hardcoded number would quietly get easier every time a Wu is added.
POINT_SHARE = 0.3

# Weighted-subset deal: a run deals a weighted sample of the pool instead of the whole thing, so a game
# stays concise as the pool grows. Sizes are the Wu left in the DRAW PILE after the opening hands; the
# boss stays short (tighter, swingier), the rest run a little longer.
PILE_SIZE = {"easy": 40, "hard": 40, "boss": 30}


@dataclass(frozen=True)
class XiaolinSettings:
    max_hand_size_player: int = 6
    max_hand_size_bot: int = 6
    starting_hand_player: int = 5
    starting_hand_bot: int = 5
    # Derived from the pool (see `pool_fingerprint`), but written out so a bare `XiaolinSettings()`
    # still deals a real game. `test_settings_defaults_match_the_card_pool` fails when they fall stale.
    max_deck_size: int = 83
    point_limit: int = 69
    starting_points_player: int = 0
    starting_points_bot: int = 0
    # How many actions (deposit / power / draw) a temple turn buys.
    actions_per_turn_player: int = 1
    actions_per_turn_bot: int = 1
    # Mercy rule: a duelist with nothing fieldable is paid this many Wu, so running dry is not an
    # auto-loss. Clamped to `max_wager` in `__post_init__`.
    empty_draw_limit: int = 1
    # The stat bar a winner must clear to claim the prize Wu.
    prize_threshold: int = 7
    max_wager: int = 3  # the most Wu either duelist may be made to stake in one showdown
    # 1: the arena element is a random roll, revealed after the wager. 0: the non-challenger picks it.
    # A 0/1 toggle on Settings.
    random_background: int = 1
    # "Three Times in a Row": a Wu committed to this many showdowns (staked, or spent as a boost) vaults
    # itself, free — see `flow.wear`.
    wear_limit: int = 3
    # What a full training bar takes; the temple tooltip reads progress/train_length.
    train_length_player: int = 10
    train_length_bot: int = 10
    # No base stat may pass this. Jack Spicer's force alone trains to one short of it — see
    # `flow.training`'s `_JACK_FORCE_MARGIN`.
    stat_cap: int = 5
    # What a lost showdown teaches the loser's training bar. A boss beating teaches double this.
    loss_fill_player: int = 1
    loss_fill_bot: int = 1

    def __post_init__(self) -> None:
        """Clamp player-entered values to a playable range, so an edited Settings screen can never
        deal a broken game (e.g. a deck smaller than the two hands, or a zero-card hand)."""
        clamp = object.__setattr__  # the dataclass is frozen; this is the sanctioned way to write
        clamp(self, "point_limit", max(2, self.point_limit))
        for hand in (
            "max_hand_size_player", "max_hand_size_bot", "starting_hand_player", "starting_hand_bot",
        ):
            clamp(self, hand, max(1, getattr(self, hand)))
        # a hand is dealt to its full starting size, so its cap can't sit below its own starting hand
        clamp(self, "max_hand_size_player", max(self.max_hand_size_player, self.starting_hand_player))
        clamp(self, "max_hand_size_bot", max(self.max_hand_size_bot, self.starting_hand_bot))
        clamp(self, "prize_threshold", max(0, self.prize_threshold))
        clamp(self, "max_wager", max(1, self.max_wager))
        clamp(self, "random_background", 1 if self.random_background else 0)  # a 0/1 toggle
        for limit in (
            "actions_per_turn_player", "actions_per_turn_bot", "empty_draw_limit", "wear_limit",
            "train_length_player", "train_length_bot", "stat_cap", "loss_fill_player", "loss_fill_bot",
        ):
            clamp(self, limit, max(1, getattr(self, limit)))
        # The mercy hand can't exceed the wager cap — `max_wager` is already clamped above, so it's
        # settled by the time we read it here.
        clamp(self, "empty_draw_limit", min(self.empty_draw_limit, self.max_wager))
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


def pile_size_for(roster: str) -> int:
    """How many Wu to leave in the draw pile after the opening hands, for a weighted deal — or ``0``
    for the whole pool, unweighted.

    The per-roster table (:data:`PILE_SIZE`) is live by default. ``XS_PILE`` overrides it: an integer
    forces that size on every roster, and ``"full"`` (or ``0``) deals the whole pool.
    """
    override = os.environ.get("XS_PILE")
    if override is None:
        return PILE_SIZE.get(roster, 0)
    if override == "full":
        return 0
    return int(override)


def roster_of(difficulty: Difficulty) -> str:
    """Which opponent roster a difficulty draws from — the string ``Catalog.opponents`` keys on.

    Folds a stale ``NORMAL`` (an older settings file, or the engine default) into Easy.
    """
    if difficulty is Difficulty.HARD:
        return "hard"
    if difficulty is Difficulty.BOSS:
        return "boss"
    return "easy"


def plays_keen(difficulty: Difficulty) -> bool:
    """Whether the bot banks by the keen rule (deposit its *most* valuable Wu).

    Hard and boss opponents both play keen; easy banks its least useful. Kept beside ``roster_of`` so
    the roster and the skill can never disagree about who is a tough opponent.
    """
    return difficulty in (Difficulty.HARD, Difficulty.BOSS)


def point_limit_for(cards: Iterable[Card], *, dealt: int | None = None) -> int:
    """Points that win the run: ``POINT_SHARE`` of the points left in the pile *after* the opening
    hands.

    Derived, not hardcoded — the pool only grows, so a fixed target gets easier with every new Wu.
    ``dealt`` is subtracted first: ten Wu sit in hands before the first showdown, and counting them
    sets a bar against cards nobody can win. Scaled by the pile's *average* card, so a rich opening
    deal shortens the run — that variance is real and unmodelled.
    """
    pile = [card for card in cards if in_pool(card.id)]
    if not pile:
        return 2
    if dealt is None:
        opening = XiaolinSettings()
        dealt = opening.starting_hand_player + opening.starting_hand_bot
    average = sum(card.points for card in pile) / len(pile)
    contested = max(1, len(pile) - dealt)
    return max(2, round(contested * average * POINT_SHARE))


def deck_size_for(cards: Iterable[Card]) -> int:
    """How many Wu a run deals — every card in the draw pool. Derived, not fixed, for the reason
    :func:`pool_fingerprint` spells out: a hardcoded deck would leave newly printed Wu out of the run."""
    return sum(1 for card in cards if in_pool(card.id))


def pool_fingerprint(cards: Iterable[Card]) -> int:
    """What the draw pool *is*, in one number: how many Wu it deals and what they are worth.

    Stored beside the settings so a saved file can tell whether it was written for **this** pool. Two
    of the settings below are not preferences at all — they are read off the pool (:func:`deck_size_for`,
    :func:`point_limit_for`) — and a settings file keeps whatever it was written with, forever.
    """
    pile = [card for card in cards if in_pool(card.id)]
    return len(pile) * 1000 + sum(card.points for card in pile)


def deal_target(roster: str, cards: Iterable[Card], settings: XiaolinSettings) -> tuple[int, int]:
    """The ``(max_deck_size, point_limit)`` a fresh game at this roster deals before any player
    override: the weighted pile's size (:data:`PILE_SIZE`) and the pool's average-value target scaled
    to it. Mirrors ``setup.py``'s weighted deal exactly, so these numbers never drift from what a game
    actually plays. ``pile <= 0`` (an unrecognised roster, or ``'full'`` via ``XS_PILE``) means the
    whole pool, unweighted — the plain pool-wide numbers.

    Single source of truth for "default" vs "customised": the Settings screen previews it per
    difficulty, and it is what a player's saved numbers are compared against for the "Modified Rules"
    star and the boss ladder's win gate (see :func:`rules_modified`).
    """
    pile = pile_size_for(roster)
    poolable = [card for card in cards if in_pool(card.id)]
    if pile <= 0:
        return deck_size_for(cards), point_limit_for(cards)
    dealt = settings.starting_hand_player + settings.starting_hand_bot
    deck_size = min(pile + dealt, len(poolable))
    point_limit = point_limit_for(poolable, dealt=max(0, len(poolable) - pile))
    return deck_size, point_limit


def default_deal(settings: Settings, cards: Iterable[Card] | None = None) -> tuple[int, int]:
    """:func:`deal_target` keyed off an engine ``Settings``' own difficulty and chosen hand sizes."""
    from ..schema.catalog import load_catalog  # local: settings must not drag the DB into every import

    cards = list(cards) if cards is not None else load_catalog().cards
    return deal_target(roster_of(settings.difficulty), cards, XiaolinSettings.from_settings(settings))


# Bumped whenever the DEAL FORMULA changes — `PILE_SIZE`, or the weighting inside `deal_target` — as
# opposed to the card pool's own content, which `pool_fingerprint` already tracks on its own. A
# settings file stamped with an older version is healed by `refreshed_for_pool` exactly like a stale
# pool, so a shipped formula tweak does not leave an existing player dealt by the old one forever.
DEAL_FORMULA_VERSION = 1


def refreshed_for_pool(settings: Settings) -> Settings:
    """Re-derive the pool-shaped settings if the pool OR the deal formula has changed since this file
    was written.

    Everything a player actually chose — difficulty, hand sizes, the thresholds, music — is kept. Only
    the two values that were never theirs to begin with are recomputed, and the new fingerprint/version
    are stamped so this happens once per change rather than every launch.
    """
    from ..schema.catalog import load_catalog  # local: settings must not drag the DB into every import

    cards = load_catalog().cards
    now = pool_fingerprint(cards)
    stale_pool = settings.options.get("pool") != now
    stale_formula = settings.options.get("deal_version") != DEAL_FORMULA_VERSION
    if not stale_pool and not stale_formula:
        return settings

    deck_size, point_limit = default_deal(settings, cards)
    return Settings(
        difficulty=settings.difficulty,
        options={
            **settings.options,
            "max_deck_size": deck_size,
            "point_limit": point_limit,
            "pool": now,
            "deal_version": DEAL_FORMULA_VERSION,
        },
    )


def rules_modified(frozen: Settings) -> bool:
    """True when the frozen settings' rule knobs differ from this difficulty's live default deal, or
    the catalog itself has been hand-edited (:func:`~..schema.catalog.catalog_tampered`) — a doctored
    ``.db`` is not the Hard/boss fight the ladder is measuring any more than a house-ruled deal is.

    Shared by :func:`save_note` (stars a customised save) and the boss ladder (:func:`ladder.record_win`
    refuses to advance on a modified ruleset).
    """
    from ..schema.catalog import catalog_tampered  # local: settings must not drag the DB into every import

    if catalog_tampered():
        return True
    saved = XiaolinSettings.from_settings(frozen)
    deck_size, point_limit = default_deal(frozen)
    default = XiaolinSettings(max_deck_size=deck_size, point_limit=point_limit)
    return saved != default


def save_note(frozen: Settings) -> SaveNote | None:
    """Mark a save that is not playing by the rules a new run would be dealt: ``*``, and nothing more.

    A save keeps the rules it was frozen with — that run *is* that game — so loading one is not a bug,
    but it may feel different for a reason nothing on screen explains. The numbers alone can't tell
    "dealt under a smaller pool" apart from "customised on purpose", so the note only claims a star,
    never a reason.
    """
    if not rules_modified(frozen):
        return None
    return SaveNote(mark="*", explanation="Modified Rules")


def default_settings() -> Settings:
    """The game's shipped defaults — the starting point for the Settings screen.

    XS runs two tiers, Easy and Hard, so it pins the difficulty rather than inheriting the engine's
    three-valued ``NORMAL`` default — the Settings screen would otherwise offer two states while a
    third sat unreachable behind them. ``turn.is_hard`` still folds any stale ``NORMAL`` into Easy.
    """
    from ..schema.catalog import load_catalog  # local: settings must not drag the DB into every import

    cards = load_catalog().cards
    base = Settings(difficulty=Difficulty.EASY)
    deck_size, point_limit = default_deal(base, cards)
    defaults = XiaolinSettings(point_limit=point_limit, max_deck_size=deck_size)
    # NO `pool` fingerprint here, and that is load-bearing. `Settings.from_dict` merges a saved file
    # *over* the defaults — so a fingerprint living in the defaults is inherited by a file that never
    # had one, and a settings file written for a pool of 20 Wu reads as current. It only ever gets
    # stamped by `refreshed_for_pool`, on a file that has actually been brought up to date.
    return defaults.to_settings(base)


# Boss-run rule: the player gets three temple actions to the boss's one.
BOSS_PLAYER_ACTIONS = 3


def deposit_limit(actions: int) -> int:
    """How many of a turn's ``actions`` may be spent depositing — half, rounded up.

    Derived from the budget rather than pinned per tier, so it cannot drift out of step with it. At
    the ordinary one action a turn it changes nothing (1 -> 1); it binds only where the budget is
    larger, which today means a boss run (3 -> 2). Extra actions are tempo, not a faster vault.
    """
    return -(-actions // 2)


def player_actions(state, settings: XiaolinSettings) -> int:
    """The PLAYER's temple-action budget this run; the opponent always plays to the settings' own.

    ``state`` is the live ``XiaolinState`` (untyped here — settings must stay importable by it).
    """
    return BOSS_PLAYER_ACTIONS if state.boss_run else settings.actions_per_turn_player
