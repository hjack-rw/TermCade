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

from termcade.app.game import SaveNote
from termcade.core.settings import Difficulty, Settings

from .constants import FIRST_DECK_CARD
from .models import Card

# A duelist wins by banking this share of the points left in the *pile* — see `point_limit_for`, which
# takes the two opening hands off the top first. Kept as a *share* so the target grows with the card
# pool: a hardcoded number would quietly get easier every time a Wu is added.
# Measured, not guessed: at 0.4 the target was decorative — 200 simulated runs ended on an empty
# pile 94% of the time, and "bank the target and the run is yours" was a promise the game almost
# never kept. At 0.3 about half of them are decided by someone actually reaching it, and the pile can
# still run out from under a duelist who dawdles. It is a *pacing* knob, not a balance one: the win
# rate did not move by a point across the whole sweep.
#
# Re-measured after the base changed from the whole pool to the pile-after-the-deal, because that made
# the old tuning meaningless: at the current target (21) **56% of easy runs end on someone banking the
# target** and 44% on an empty pile — which is the split this number was chosen for, kept. Win rate is
# still flat across 17/21/25/28, so it is still pacing. (The hard tier ends on the target 93% of the
# time: that opponent banks its way to the win rather than grinding you out of cards.)
POINT_SHARE = 0.3


@dataclass(frozen=True)
class XiaolinSettings:
    max_hand_size: int = 6
    starting_hand_player: int = 5
    starting_hand_bot: int = 5
    # Both track the card pool, and `default_settings` recomputes them from it. They are written out
    # here too because a bare `XiaolinSettings()` deals a real game: a stale `max_deck_size` would
    # shuffle the pool and then truncate it, quietly leaving the newest Wu out of the run.
    # `test_settings_defaults_match_the_card_pool` fails when a printed Wu leaves them behind.
    max_deck_size: int = 40
    point_limit: int = 21
    starting_points_player: int = 0
    starting_points_bot: int = 0
    # One vault turn, one action: bank a Wu, spend a Wu's power, or draw one off your own deck.
    # They come out of the same budget on purpose — that is what makes a hand a resource rather than
    # a thing that refills itself, and it prices every Wu whose power is worth more than its points.
    actions_per_turn: int = 1
    # The mercy rule: a duelist with nothing they can field is dealt back in, to this many Wu. Running
    # out must not be an auto-loss — that would end a run on a dealt hand rather than on a played one.
    #
    # But it is *income*, and it is paid to whoever is losing: a hand empties because it was staked and
    # forfeited, and the refill comes off the contested pile (your own shelf answers first, but a
    # duelist who keeps losing never overflows their hand, so their shelf is bare). Measured, it fires
    # ~3.8 times a run and hands the losing side ~7.5 Wu off a pile of ~30 — the largest single source
    # of Wu in the game.
    #
    # So it is CLAMPED to `max_wager` in `__post_init__`: you are dealt back in, but never dealt more
    # than you could have staked. This is a **guardrail, not a lock** — nobody raising a number on the
    # Settings screen is cheating, that screen is there to build a custom game. It is there so a player
    # cannot quietly wreck their own run without knowing they did: unclamped, nudging this from 3 to 4
    # took the hard tier from 37% to 72% and to 75% at 5, and nothing on screen would have said why the
    # game had stopped being hard.
    empty_draw_limit: int = 3
    # The bar a winner's stats must clear to claim the prize Wu — the one number deciding whether Wu
    # circulate or the pile just drains. Measured across 6..9 (see BALANCE.md): 7 is the only value at
    # which all four routes of the prize cascade actually fire. Below it the decisive blow claims
    # everything and the routes beneath it never get a turn; above it the middle two collapse and the
    # elemental fallback becomes the main way a Wu is won, which inverts the cascade. Tunable rather
    # than derived: it turns on character stats AND card stats together.
    prize_threshold: int = 7
    # The Early Bird: outrun the other duelist by this much initiative and you may take the next Wu
    # off the pile with no showdown, surrendering your fastest Wu for it. Three is the author's number
    # and it is deliberately hard to reach — equal bonuses do not stack, so it takes a +1 beside a +2,
    # or their -2 plus your +1. Lower it and the showdown stops being how Wu change hands.
    early_bird_gap: int = 3
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
        clamp(self, "early_bird_gap", max(1, self.early_bird_gap))
        for limit in ("actions_per_turn", "empty_draw_limit"):
            clamp(self, limit, max(1, getattr(self, limit)))
        # The mercy hand can never exceed the wager cap: being dealt back in must not pay better than
        # playing well. `max_wager` is clamped above this, so it is settled by the time we read it.
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


def is_hard(difficulty: Difficulty) -> bool:
    """The game runs two tiers, not three: only HARD is the hard tier.

    Picks the opponent roster (``Catalog.opponents``) and the bot's deposit skill alike, so the two
    can never disagree. Folds a stale ``NORMAL`` (an older settings file, or the engine default)
    into Easy.
    """
    return difficulty is Difficulty.HARD


def point_limit_for(cards: Iterable[Card], *, dealt: int | None = None) -> int:
    """How many points win the run — a share of the points still *in the pile* once hands are dealt.

    Derived, not hardcoded: the pool only ever grows, and a fixed target would quietly get easier
    with every Wu added. The player can still override it on the Settings screen; this is only what
    the game ships with.

    ``dealt`` is what the two opening hands take off the top, and it is subtracted before the share
    is taken. The pile — not the printed pool — is what a run is actually fought over: ten Wu are in
    somebody's hand before a single showdown is called. Counting them toward the bar sets a target
    against cards nobody has to win.

    Which Wu land in those hands is random, so this cannot know their points — it scales by the
    pile's *average* card instead. **Ten cards of various points is not a fixed number of points**:
    a fat deal can take 30 off the table and a lean one barely 10, and the same target is set either
    way. That variance is real and it is not modelled — it makes a run with a rich opening hand a
    shorter run. Averaging is the only honest option here (a target is chosen before a card is dealt),
    but do not read the number as though the hands always cost the same.

    A Xiaolin duelist is dealt one fewer (their birthright fills the slot), so the real pile is 30 or
    31; that difference is one average card, well inside the rounding.
    """
    pile = [card for card in cards if card.id >= FIRST_DECK_CARD]
    if not pile:
        return 2
    if dealt is None:
        opening = XiaolinSettings()
        dealt = opening.starting_hand_player + opening.starting_hand_bot
    average = sum(card.points for card in pile) / len(pile)
    contested = max(1, len(pile) - dealt)
    return max(2, round(contested * average * POINT_SHARE))


def deck_size_for(cards: Iterable[Card]) -> int:
    """How many Wu a run deals — every card in the draw pool.

    Derived for the same reason as :func:`point_limit_for`: the pool grows as Wu are printed, and a
    hardcoded deck would quietly leave the newest ones out of the run. Deal fewer than the pool and
    ``new_game`` shuffles, then truncates — so a Wu would sit out at random, and the win target
    (a share of *every* card's points) would still be counting the points it took with it.
    """
    return sum(1 for card in cards if card.id >= FIRST_DECK_CARD)


def pool_fingerprint(cards: Iterable[Card]) -> int:
    """What the draw pool *is*, in one number: how many Wu it deals and what they are worth.

    Stored beside the settings so a saved file can tell whether it was written for **this** pool. Two
    of the settings below are not preferences at all — they are read off the pool (:func:`deck_size_for`,
    :func:`point_limit_for`) — and a settings file keeps whatever it was written with, forever.

    That is not hypothetical. A `settings.json` written when the pool held ~20 Wu pinned
    `max_deck_size = 20` and `point_limit = 13`; the pool then grew to 40, and every run since dealt
    **half the pool at random** (`new_game` shuffles, then truncates) and ended on a target meant for a
    game half this size. Every Wu printed after that file was written could simply fail to appear.
    """
    pile = [card for card in cards if card.id >= FIRST_DECK_CARD]
    return len(pile) * 1000 + sum(card.points for card in pile)


def refreshed_for_pool(settings: Settings) -> Settings:
    """Re-derive the pool-shaped settings if the pool has changed since this file was written.

    Everything a player actually chose — difficulty, hand sizes, the thresholds, music — is kept. Only
    the two values that were never theirs to begin with are recomputed, and the new fingerprint is
    stamped so this happens once per pool change rather than every launch.
    """
    from .catalog import load_catalog  # local: settings must not drag the DB into every import

    cards = load_catalog().cards
    now = pool_fingerprint(cards)
    if settings.options.get("pool") == now:
        return settings

    return Settings(
        difficulty=settings.difficulty,
        options={
            **settings.options,
            "max_deck_size": deck_size_for(cards),
            "point_limit": point_limit_for(cards),
            "pool": now,
        },
    )


def save_note(frozen: Settings) -> SaveNote | None:
    """Mark a save that is not playing by the rules a new run would be dealt: ``*``, and nothing more.

    A save keeps the rules it was frozen with — that run *is* that game — so loading one is not a bug.
    But it will feel different for a reason nothing on screen explains: it may have been dealt a
    smaller pile, or a target the player set by hand.

    **A star, because a star is all this can honestly claim.** The first version said "older rules",
    which asserted a *provenance it never checked*: a run where the player deliberately set their own
    target got labelled old. The numbers alone cannot tell "dealt under a smaller pool" apart from
    "customised on purpose", and a note that guesses is worse than a note that points.
    """
    from .catalog import load_catalog  # local: settings must not drag the DB into every import

    cards = load_catalog().cards
    saved = XiaolinSettings.from_settings(frozen)
    default = XiaolinSettings(
        max_deck_size=deck_size_for(cards), point_limit=point_limit_for(cards)
    )
    if saved == default:
        return None
    return SaveNote(mark="*", explanation="Modified Rules")


def default_settings() -> Settings:
    """The game's shipped defaults — the starting point for the Settings screen.

    XS runs two tiers, Easy and Hard, so it pins the difficulty rather than inheriting the engine's
    three-valued ``NORMAL`` default — the Settings screen would otherwise offer two states while a
    third sat unreachable behind them. ``turn.is_hard`` still folds any stale ``NORMAL`` into Easy.
    """
    from .catalog import load_catalog  # local: settings must not drag the DB into every import

    cards = load_catalog().cards
    defaults = XiaolinSettings(
        point_limit=point_limit_for(cards), max_deck_size=deck_size_for(cards)
    )
    # NO `pool` fingerprint here, and that is load-bearing. `Settings.from_dict` merges a saved file
    # *over* the defaults — so a fingerprint living in the defaults is inherited by a file that never
    # had one, and a settings file written for a pool of 20 Wu reads as current. It only ever gets
    # stamped by `refreshed_for_pool`, on a file that has actually been brought up to date.
    return defaults.to_settings(Settings(difficulty=Difficulty.EASY))
