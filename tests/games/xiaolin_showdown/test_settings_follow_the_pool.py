"""Two of the settings are not preferences: they are read off the card pool.

``max_deck_size`` and ``point_limit`` come from `deck_size_for` / `point_limit_for`. A settings file
keeps whatever it was written with — right for a preference, wrong for a derived value. A real file
written when the pool held ~20 Wu went on dealing **20 of 40 cards** (`new_game` shuffles, then
truncates, so half the pool never appeared) and ending at a target meant for a game half the size.

The rule, and the reason there are two tests here rather than one:

- ``settings.json`` is what a **new** run is dealt with, so it follows the pool.
- a **save** froze its settings at new-game. That run *is* that game, and loading it must not retro-fit
  the current pool's numbers onto a game already in progress.
"""

from __future__ import annotations

import json

from termcade.core.settings import Settings
from textual.widgets import Button

from termcade.ui.app import EngineApp

from xiaolin_showdown.game import build_game
from xiaolin_showdown.logic.state import XiaolinState
from xiaolin_showdown.logic.catalog import load_catalog
from xiaolin_showdown.logic.settings import (
    XiaolinSettings,
    default_settings,
    deck_size_for,
    point_limit_for,
    refreshed_for_pool,
    save_note,
)


def _stale() -> Settings:
    """The file as it really was: written for a pool of about twenty Wu — and with **no fingerprint**.

    That absence is the test. An earlier version of this seeded a stale fingerprint (`"pool": 999`),
    which no real file has ever carried — and it hid the bug it was written to catch: the fingerprint
    was being shipped in the *defaults*, `Settings.from_dict` merges a saved file over the defaults, so
    a file that had never heard of a fingerprint inherited the current one and read as up to date. The
    tmp-dir test went green while the real file went on dealing half the pool.
    """
    return Settings(options={"max_deck_size": 20, "point_limit": 13, "max_hand_size": 6})


def test_a_file_written_for_a_smaller_pool_is_brought_up_to_date():
    cards = load_catalog().cards

    fresh = XiaolinSettings.from_settings(refreshed_for_pool(_stale()))

    assert fresh.max_deck_size == deck_size_for(cards)
    assert fresh.point_limit == point_limit_for(cards)


def test_the_defaults_carry_no_fingerprint_of_their_own():
    """The one that would have caught the real bug.

    A fingerprint in the shipped defaults is inherited by every saved file (`from_dict` merges the file
    *over* them), so nothing ever looks stale and nothing is ever refreshed. It may only be stamped on
    a file that has actually been brought up to date.
    """
    assert "pool" not in default_settings().options


def test_what_the_player_actually_chose_survives_the_refresh():
    """Only the two values that were never theirs are recomputed. Everything else is a preference."""
    chosen = Settings(options={**_stale().options, "max_hand_size": 9, "prize_threshold": 5})

    kept = XiaolinSettings.from_settings(refreshed_for_pool(chosen))

    assert kept.max_hand_size == 9
    assert kept.prize_threshold == 5


def test_a_file_already_written_for_this_pool_is_left_alone():
    """The fingerprint is what makes this happen once per pool change, not on every launch."""
    current = refreshed_for_pool(_stale())

    assert refreshed_for_pool(current) == current


async def test_booting_the_game_heals_a_stale_file_on_disk(tmp_path):
    """It is not enough to correct it in memory: the next launch must find it right.

    Through the real `EngineApp`, because that is where it broke — the pure function was correct all
    along, and the game still dealt half the pool.
    """
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"difficulty": "easy", "options": _stale().options}), encoding="utf-8")

    app = EngineApp(build_game(), data_dir=tmp_path, seed=1)
    async with app.run_test() as pilot:
        await pilot.pause()

        on_disk = json.loads(path.read_text(encoding="utf-8"))["options"]
        assert on_disk["max_deck_size"] == deck_size_for(load_catalog().cards)
        assert on_disk["point_limit"] == point_limit_for(load_catalog().cards)


async def test_a_run_already_saved_keeps_the_rules_it_was_dealt(tmp_path, catalog):
    """A save froze its settings at new-game. That run is that game — loading it changes no rule.

    This is the other half of the promise: the pool may have grown since, and the *next* run will be
    dealt the bigger game. The one already in progress is not re-dealt underneath the player.
    """
    from termcade.core.rng import Rng

    from xiaolin_showdown.logic.setup import new_game

    old_rules = XiaolinSettings(max_deck_size=20, point_limit=13)
    state = new_game(catalog, Rng(1), catalog.character(1), settings=old_rules)

    app = EngineApp(build_game(), data_dir=tmp_path, seed=1)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.ctx.saves.save(
            0, state, Rng(1), title="an older run", settings=old_rules.to_settings()
        )
        _state, _rng, _meta, settings = app.ctx.saves.load(0, XiaolinState, app.ctx)

    frozen = XiaolinSettings.from_settings(settings)

    assert frozen.point_limit == 13  # the run it was dealt, not the run the pool now describes
    assert frozen.max_deck_size == 20


# --- the other half: a save keeps its rules, and the slot says so --------------------------------


def test_a_save_dealt_the_current_pool_needs_no_note():
    """The note is for a run that plays differently. A current one is just a save."""
    cards = load_catalog().cards
    current = XiaolinSettings(
        max_deck_size=deck_size_for(cards), point_limit=point_limit_for(cards)
    ).to_settings()

    assert save_note(current) is None


def test_a_save_playing_by_other_rules_is_starred():
    """A star, and nothing more.

    The first version said "older rules", which claimed a *provenance it never checked*: the numbers
    alone cannot tell "dealt under a smaller pool" apart from "the player set their own target". A note
    that guesses is worse than a note that points.
    """
    older = XiaolinSettings(max_deck_size=20, point_limit=13).to_settings()

    note = save_note(older)

    assert note is not None
    assert note.mark == "*"


def test_a_hand_tuned_run_is_starred_the_same_way():
    """Customised on purpose, not old — and the mark makes no claim about which."""
    custom = XiaolinSettings(prize_threshold=9).to_settings()

    note = save_note(custom)

    assert note is not None
    assert note.mark == "*"


def test_the_star_explains_itself_on_hover():
    """A star nobody can decode is noise. The label has room for a character; the tooltip has room for
    the sentence."""
    custom = XiaolinSettings(prize_threshold=9).to_settings()

    note = save_note(custom)

    assert note is not None
    assert note.explanation == "Modified Rules"


async def test_the_slot_marks_the_save_beside_its_name(tmp_path, catalog):
    """Through the real screen: a player learns this where they pick the save, or not at all."""
    from termcade.core.rng import Rng
    from termcade.ui.screens.save_slot import SaveSlotScreen

    from xiaolin_showdown.logic.setup import new_game

    older = XiaolinSettings(max_deck_size=20, point_limit=13)
    state = new_game(catalog, Rng(1), catalog.character(1), settings=older)

    app = EngineApp(build_game(), data_dir=tmp_path, seed=1)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.ctx.saves.save(0, state, Rng(1), title="an older run", settings=older.to_settings())

        app.push_screen(SaveSlotScreen(mode="load"))
        await pilot.pause()

        marked = app.screen.menu_items()[0]
        hover = app.screen.query_one("#slot-0", Button).tooltip

    assert "*" in marked.label  # the mark a player sees at a glance
    assert hover == "Modified Rules"  # ...and what it means when they ask
