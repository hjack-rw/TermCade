"""The page Back button's key, and the guard that a fast finger cannot outrun.

The button used to send Escape, which each screen is free to give its own meaning — on the game's
hub that meaning is "abandon this run for the main menu". Its only protection was hiding itself when
the app said going back was not allowed, and that answer travels a round trip behind the tap: press
twice quickly and the second press landed on a hub that read it as Escape. So the key has one
meaning now, and the guard is re-checked in the app at the moment the key arrives.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static

from termcade.ui.screens.base import EngineScreen


class _Root(EngineScreen):
    def compose(self) -> ComposeResult:
        yield Static("root", id="root")


class _Deeper(EngineScreen):
    def compose(self) -> ComposeResult:
        yield Static("deeper", id="deeper")


class _NoWayBack(EngineScreen):
    """A hub: something is running here, so leaving is not a thing the Back button may do."""

    BACK_ALLOWED = False

    def compose(self) -> ComposeResult:
        yield Static("hub", id="hub")


class _HubWithEscape(_NoWayBack):
    """As the game's hub really is: no Back button, but Escape leaves — and says so in the footer."""

    BINDINGS = [("escape", "app.pop_screen", "Menu")]


async def test_the_back_key_pops_one_screen(make_app):
    app = make_app(_Root)
    async with app.run_test() as pilot:
        app.push_screen(_Deeper())
        await pilot.pause()
        assert isinstance(app.screen, _Deeper)

        await pilot.press(EngineScreen.BACK_KEY)
        await pilot.pause()

        assert isinstance(app.screen, _Root)


async def test_a_burst_of_presses_stops_at_the_screen_that_refuses(make_app):
    """The bug as reported: tapping fast walked straight off the hub and dropped the run."""
    app = make_app(_Root)
    async with app.run_test() as pilot:
        app.push_screen(_NoWayBack())
        await pilot.pause()
        app.push_screen(_Deeper())
        await pilot.pause()

        for _ in range(8):
            await pilot.press(EngineScreen.BACK_KEY)
            await pilot.pause()

        assert isinstance(app.screen, _NoWayBack), "the hub must absorb every press after the first"


async def test_the_key_never_pops_the_games_root(make_app):
    """Nothing under the root but the app itself — a press here would put the player nowhere."""
    app = make_app(_Root)
    async with app.run_test() as pilot:
        await pilot.pause()
        for _ in range(5):
            await pilot.press(EngineScreen.BACK_KEY)
            await pilot.pause()
        assert isinstance(app.screen, _Root)


async def test_escape_still_leaves_a_hub_that_binds_it(make_app):
    """The temple's exact shape: ``BACK_ALLOWED = False`` *and* an escape binding that leaves.

    The keyboard must be untouched by this fix — a player at a terminal presses Escape and goes to
    the menu, as the footer promises. Only the page's button is refused, and only because a finger
    cannot tell it apart from the tap before it.
    """
    app = make_app(_Root)
    async with app.run_test() as pilot:
        app.push_screen(_HubWithEscape())
        await pilot.pause()

        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, _Root), "escape is the screen's own business"

        app.push_screen(_HubWithEscape())
        await pilot.pause()
        await pilot.press(EngineScreen.BACK_KEY)
        await pilot.pause()
        assert isinstance(app.screen, _HubWithEscape), "the page's button is not escape"


class _Replaces(EngineScreen):
    """A screen that REPLACED what it came from, so popping it lands somewhere else entirely."""

    went_back = False

    def compose(self) -> ComposeResult:
        yield Static("replaces", id="replaces")

    def page_back(self) -> None:
        self.went_back = True


async def test_a_screen_decides_for_itself_what_going_back_means(make_app):
    """Popping is the default, not the rule.

    A duel replaces the temple rather than stacking on it, so popping one lands on the main menu and
    throws the run away — there, back means Retreat. That distinction used to live in a handler for
    the Back *widget*, and when the widget went away the page's button walked straight past it and
    abandoned live runs.
    """
    app = make_app(_Root)
    async with app.run_test() as pilot:
        app.push_screen(_Replaces())
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, _Replaces)

        await pilot.press(EngineScreen.BACK_KEY)
        await pilot.pause()

        assert screen.went_back, "the screen's own answer was not asked for"
        assert app.screen is screen, "the default pop ran anyway and took the screen with it"
