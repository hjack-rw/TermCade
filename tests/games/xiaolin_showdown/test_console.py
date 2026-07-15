"""The dev console — the tool that makes a new Wu testable.

A card is worth whatever it does in a real showdown, and a 40-card pile deals it to you when it feels
like it. That is not a test, it is a wait. So the console deals the Wu into a hand, stacks the pile with
the one you want fought over, and lets you go and play the thing you are judging.

**Every command acts on the live run.** A conjured Wu is fielded, boosted, cursed and scored by exactly
the rules a dealt one would be — a sandbox that plays by its own rules tests nothing, and that is the
invariant most of these tests are really about.
"""

from __future__ import annotations

import pytest
from textual.color import Color
from textual.widgets import Input, Static

from termcade.ui.app import EngineApp
from termcade.ui.screens.console import DEBUG_ENV, ConsoleScreen

from xiaolin_showdown.console import COMMANDS
from xiaolin_showdown.game import build_game
from xiaolin_showdown.screens.temple import TempleScreen

ROOSTER_BOOSTER = 43
SHIMO_STAFF = 44
FIST_OF_TEBIGONG = 6


@pytest.fixture(autouse=True)
def _debug_build(monkeypatch):
    """Every test here needs a *development* build — the console does not exist in a shipped one."""
    monkeypatch.setenv(DEBUG_ENV, "1")


@pytest.fixture
def console(tmp_path, state):
    """A run in progress, with the console open over it."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _console():
        app = EngineApp(build_game(), data_dir=tmp_path, seed=1)
        async with app.run_test(size=(150, 50)) as pilot:
            await pilot.pause()
            app.ctx.state = state
            app.push_screen(TempleScreen())
            await pilot.pause()
            await pilot.press("grave_accent")  # the key a terminal really sends for `
            await pilot.pause()

            async def run(command: str) -> None:
                app.screen.query_one("#console-input", Input).value = command
                await pilot.press("enter")
                await pilot.pause()

            async def toggle() -> None:
                await pilot.press("grave_accent")
                await pilot.pause()
                await pilot.pause()

            app._press_console_key = toggle  # type: ignore[attr-defined]
            yield app, run

    return _console


async def test_the_backtick_opens_it_over_a_running_game(console):
    async with console() as (app, _run):
        assert isinstance(app.screen, ConsoleScreen)


async def test_it_floats_over_the_game_rather_than_replacing_it(console):
    """A pop-up, not a screen instead of the game: you conjure a Wu and watch the hand it lands in.

    Opaque and full-screen, the console would hide the very thing it exists to change.
    """
    async with console() as (app, _run):
        assert isinstance(app.screen, ConsoleScreen)
        assert isinstance(app.screen_stack[-2], TempleScreen)  # the board is still there, underneath
        assert app.screen.styles.background.a < 1  # ...and it shows through


async def test_the_key_that_opens_it_shuts_it(console):
    """A console you must reach for Escape to leave is a console you stop opening.

    Three things had to be true for this, and each one broke first: the *app* owns the toggle (an
    app-level priority binding fires before any of the console's own, so a close binding on the console
    raced the open binding and they re-pushed each other), and the **field itself** refuses the key — a
    focused Input swallows every printable character to type it, before any binding is consulted at all.
    """
    async with console() as (app, _run):
        await app._press_console_key()

        assert isinstance(app.screen, TempleScreen)


async def test_the_closing_key_is_never_typed_into_the_field(console):
    """The bug underneath: the backtick was being typed into the console instead of closing it."""
    async with console() as (app, _run):
        box = app.screen.query_one("#console-input", Input)
        await app._press_console_key()

        assert box.value == ""


async def test_nothing_in_the_game_advertises_it(console):
    """Hidden on purpose: `~` and nothing else. A player who has not been told will not find it."""
    async with console() as (app, _run):
        shown = [e.binding.key for e in app.screen.active_bindings.values() if e.binding.show]

        assert "~" not in shown


def _ids(cards) -> set[int]:
    """By id, never by identity.

    `mechanics.cards.is_one_of` is the game's own "is this the same Wu" test and it compares by
    *identity* — which the console deliberately breaks: it deals a **copy**, because the duel scribbles
    on what it is handed. Asserting identity here would be asserting the bug back in.
    """
    return {card.id for card in cards}


async def test_give_puts_a_wu_in_your_hand(console, state):
    """The command the whole console exists for."""
    async with console() as (app, run):
        await run(f"give {ROOSTER_BOOSTER} {SHIMO_STAFF}")

    assert {ROOSTER_BOOSTER, SHIMO_STAFF} <= _ids(state.player.hand)


async def test_a_conjured_wu_is_a_real_wu(console, state, catalog):
    """It is a *copy*, not the catalog's own card — the duel mutates what it is handed.

    Hand it the catalog's card and a showdown would scribble on the game's own data. This is the bug
    the whole `logic/mechanics/cards.py` identity rule exists to prevent, and the console is a new door
    into it.
    """
    async with console() as (app, run):
        await run(f"give {ROOSTER_BOOSTER}")

    dealt = next(c for c in state.player.hand if c.id == ROOSTER_BOOSTER)

    assert dealt is not catalog.card(ROOSTER_BOOSTER)  # a copy
    assert dealt.stats == catalog.card(ROOSTER_BOOSTER).stats  # ...of the real thing


async def test_givebot_arms_the_opponent(console, state):
    """A Wu is only tested once it has been played *against* you."""
    async with console() as (app, run):
        await run(f"givebot {SHIMO_STAFF}")

    assert SHIMO_STAFF in _ids(state.bot.hand)


async def test_pile_stacks_the_next_showdown(console, state):
    """So the next duel is fought over the Wu you want to see fought over."""
    async with console() as (app, run):
        await run(f"pile {SHIMO_STAFF}")

    assert state.card_deck[0].id == SHIMO_STAFF


async def test_deck_shelves_onto_the_opponents_personal_deck(console, state):
    """What the deck powers read and pull from — testable at last without waiting for a hand to overflow."""
    async with console() as (app, run):
        await run(f"deck them {SHIMO_STAFF}")

    assert SHIMO_STAFF in _ids(state.bot.deck)


async def test_lose_feeds_the_lost_pile(console, state):
    """The Rooster Booster's whole reason to exist, and otherwise a wait for a showdown to end badly."""
    async with console() as (app, run):
        await run(f"lose {FIST_OF_TEBIGONG}")

    assert FIST_OF_TEBIGONG in _ids(state.lost)


async def test_points_skips_to_the_end_of_a_run(console, state):
    """To play the last turn of a race without playing the race."""
    async with console() as (app, run):
        await run("points 19 4")

    assert (state.player.points, state.bot.points) == (19, 4)


async def test_a_command_that_raises_does_not_take_the_game_with_it(console):
    """A console is where a person experiments, and experiments raise. One that killed the run would be
    useless for the thing it exists for."""
    async with console() as (app, run):
        await run("give 9999")  # no such Wu
        await run("nonsense")  # no such command

        assert isinstance(app.screen, ConsoleScreen)  # still standing


async def test_every_command_says_what_it_does():
    """`help` is the only way in — a command nobody can describe is a command nobody will use."""
    for name, command in COMMANDS.items():
        assert command.help.startswith(name), f"{name}'s help does not say how to call it"


async def test_the_prompt_looks_like_something_you_can_type_into(console):
    """The bug this catches: a bare Input on a dark panel is invisible.

    Its border sat one shade off the panel, its background resolved transparent, and an empty field has
    nothing in it to see — so the console opened looking like a wall of text with no way in. A caret and
    a real background are what say "type here".
    """
    async with console() as (app, _run):
        row = app.screen.query_one("#console-prompt")
        caret = app.screen.query_one("#console-caret", Static)
        box = app.screen.query_one("#console-input", Input)

        assert row.styles.background != Color(0, 0, 0, 0)  # not transparent
        assert row.size.height >= 1 and caret.size.width >= 1  # the caret is actually on screen
        assert box.placeholder  # ...and the field says what to type into it


async def test_the_cursor_is_in_the_field_the_moment_it_opens(console):
    """`~` is a keystroke, and the next thing a person does is type. Asking them to click first is rude."""
    async with console() as (app, _run):
        assert app.screen.focused is app.screen.query_one("#console-input", Input)


async def test_it_does_not_open_where_there_is_no_game(tmp_path):
    """Every command acts on a run — deal a Wu, stack a pile, set the score.

    On the start menu there is nothing to act on, so a console would be a box whose every answer is
    "there is no game". It opens where it can do something and stays shut where it cannot.
    """
    from xiaolin_showdown.screens.start import StartScreen

    app = EngineApp(build_game(), data_dir=tmp_path, seed=1)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, StartScreen)  # no run yet
        assert app.ctx.state is None

        await pilot.press("grave_accent")
        await pilot.pause()

        assert isinstance(app.screen, StartScreen)  # nothing happened, and nothing should have


async def test_a_shipped_build_has_no_console_at_all(tmp_path, state, monkeypatch):
    """Locked, not hidden. Without `TERMCADE_DEBUG` the key does nothing and the screen is never built.

    A tool that can deal a player any Wu in the game is worth the difference between "you will not find
    it" and "it is not there".
    """
    monkeypatch.delenv(DEBUG_ENV, raising=False)

    app = EngineApp(build_game(), data_dir=tmp_path, seed=1)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.ctx.state = state
        app.push_screen(TempleScreen())
        await pilot.pause()

        await pilot.press("grave_accent")
        await pilot.pause()

        assert isinstance(app.screen, TempleScreen)  # the key did nothing at all


async def test_the_switch_takes_the_usual_words(monkeypatch):
    """`1`, `true`, `yes`, `on` — and anything else is a shipped build."""
    from termcade.ui.screens.console import debug_enabled

    for word in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv(DEBUG_ENV, word)
        assert debug_enabled(), word

    for word in ("", "0", "false", "no", "maybe"):
        monkeypatch.setenv(DEBUG_ENV, word)
        assert not debug_enabled(), word


async def test_refresh_gives_the_turns_action_back(console, state):
    """Spend a power, get the action back, spend another — several in one vault turn.

    The one-action economy is what makes a hand a resource, and it is also what makes testing a power
    slow: two powers cost two turns and a showdown in between. This is the command that pays that back.
    """
    state.actions_taken = 1  # the turn is spent

    async with console() as (app, run):
        await run("refresh")

    assert state.actions_taken == 0


async def test_refresh_can_hand_the_opponent_theirs_back(console, state):
    """A card is only tested once it has been used *against* you."""
    state.bot_actions_taken = 1

    async with console() as (app, run):
        await run("refresh them")

    assert state.bot_actions_taken == 0


async def test_refresh_both_at_once(console, state):
    state.actions_taken = state.bot_actions_taken = 1

    async with console() as (app, run):
        await run("refresh both")

    assert (state.actions_taken, state.bot_actions_taken) == (0, 0)
