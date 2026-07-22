"""The focus key advertises itself in the footer — but only where focus has somewhere to go.

Tab moves focus in every Textual app and says so in none of them, and `EngineScreen.AUTO_FOCUS = ""`
makes that worse here: nothing starts focused, so nothing hints that focus is a thing at all. A key a
player cannot discover is a key they do not have.

**These tests ask the footer, and that is the whole point of them.** The first version asked
`check_action`, which only says a binding is *allowed* — it passed while the footer stayed empty,
because `EngineApp` binds Tab itself with `priority=True`, and an app-level priority binding beats any
screen's. A test that cannot see what the player sees will happily bless a key nobody can find.
"""

from __future__ import annotations

import pytest
from textual.widgets import Footer, Input, Static
from textual.widgets._footer import FooterKey

from termcade.app.game import Game
from termcade.core.settings import Settings
from termcade.ui.app import EngineApp
from termcade.ui.screens.base import TOUCH_ENV, EngineScreen


class _WithFooter(EngineScreen):
    """A screen that actually draws a Footer, so the test can read what the player is offered."""

    def compose(self):
        yield Input(id="one")
        yield Input(id="two")
        yield Footer()


class _Focusable(EngineScreen):
    """A screen a player can move focus around — a search box, say."""

    def compose(self):
        yield Input(id="box")


class _JustText(EngineScreen):
    """A screen of plain text, like the vault board or an outcome."""

    def compose(self):
        yield Static("nothing here can take focus")


def _game(root) -> Game:
    return Game(
        game_id="focus-test",
        title="Focus",
        state_cls=None,
        default_settings=Settings(),
        saves_enabled=False,
        root_screen=root,
    )


@pytest.fixture
def app(tmp_path):
    def _app(screen_cls):
        return EngineApp(_game(screen_cls), data_dir=tmp_path, seed=1)

    return _app


def _footer_keys(app) -> dict[str, bool]:
    """Every key the footer draws, and whether it is *live* on this screen.

    Read off ``active_bindings`` — the same thing ``Footer`` renders from — rather than off
    ``check_action``, which answers a different question ("may this fire?") and answered it happily
    while the key stayed invisible. `Footer.compose` filters on ``binding.show`` and dims the rest, so
    a disabled key is greyed, not gone.
    """
    return {
        entry.binding.key: entry.enabled
        for entry in app.screen.active_bindings.values()
        if entry.binding.show
    }


async def test_the_footer_offers_the_focus_key_where_focus_can_go(app):
    async with app(_Focusable).run_test() as pilot:
        await pilot.pause()

        assert _footer_keys(pilot.app)["tab"] is True  # listed, and live


async def test_the_focus_key_is_dead_on_a_screen_with_nothing_to_focus(app):
    """Greyed, not gone — Textual's Footer dims a disabled binding rather than dropping it.

    So the key is always *listed* (a player learns it exists) and only *live* where it does something.
    The earlier version of this test asserted it vanished entirely, which is not what Textual does.
    """
    async with app(_JustText).run_test() as pilot:
        await pilot.pause()

        assert _footer_keys(pilot.app)["tab"] is False


async def test_pressing_it_enters_focus_mode(app):
    """Nothing is focused until Tab is pressed — which is why the key has to announce itself at all."""
    async with app(_Focusable).run_test() as pilot:
        await pilot.pause()
        assert pilot.app.screen.focused is None  # nothing looks pre-selected on a fresh screen

        await pilot.press("tab")
        await pilot.pause()

        assert pilot.app.screen.focused is pilot.app.screen.query_one("#box", Input)


async def test_pressing_it_again_leaves_focus_mode(app):
    """It is a *toggle*: a second press steps back out rather than cycling to the same widget."""
    async with app(_Focusable).run_test() as pilot:
        await pilot.pause()
        await pilot.press("tab")
        await pilot.pause()

        await pilot.press("tab")
        await pilot.pause()

        assert pilot.app.screen.focused is None


async def test_a_phone_is_not_offered_focus_mode(make_app, monkeypatch):
    """Focus mode is a way to drive the game with keys a phone does not have — no Tab to enter it,
    no arrows to move inside it. Advertising it spends a slot in the most crowded row on a 6cm
    screen, and the footer is the only place the game tells a player what it can do."""
    monkeypatch.setenv(TOUCH_ENV, "1")
    app = make_app(_WithFooter)
    async with app.run_test() as pilot:
        await pilot.pause()
        keys = {key.key for key in app.screen.query_one(Footer).query(FooterKey)}
        assert "tab" not in keys, f"the phone is still shown a key it cannot press: {keys}"

        # And it must be OFF, not merely hidden. `check_action` returning False does not stop a
        # `priority=True` binding — hiding the key alone left Tab fully live, which on a tablet with
        # a keyboard case drops the player into a mode whose exit is no longer advertised.
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused is None, "focus mode still fires on a touch session"
        await pilot.press("down")
        await pilot.pause()
        assert app.focused is None, "the arrows still move focus on a touch session"


async def test_a_terminal_still_gets_it(make_app):
    """The other half of the claim — this must be a touch concession, not a removal."""
    app = make_app(_WithFooter)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused is not None, "focus mode stopped working where it is the only way to nav"
