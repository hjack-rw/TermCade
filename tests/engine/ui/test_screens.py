"""Engine screen mechanics (headless Pilot): MenuScreen dispatch, ChoiceModal dialogs, and the
save picker's corrupt-save handling. No game logic — a fake game supplies the context only."""

from __future__ import annotations

import sqlite3

from textual import work
from textual.app import ComposeResult
from textual.widgets import Button, Static

from termcade.ui.screens.base import EngineScreen
from termcade.ui.screens.dialog import ChoiceModal
from termcade.ui.screens.menu import MenuItem, MenuScreen
from termcade.ui.screens.save_slot import SaveSlotScreen


class _MenuProbe(MenuScreen):
    menu_title = "PROBE"
    menu_description = "pick one"
    selected: str | None = None

    def menu_items(self) -> list[MenuItem]:
        return [MenuItem("a", "Alpha"), MenuItem("b", "Beta", disabled=True)]

    def on_select(self, item_id: str) -> None:
        self.selected = item_id


class _Blank(EngineScreen):
    def compose(self) -> ComposeResult:
        yield Static("blank", id="blank")


# --- MenuScreen ----------------------------------------------------------------


async def test_menuscreen_shows_its_description(make_app):
    app = make_app(_MenuProbe)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert str(app.screen.query_one(".panel-desc", Static).render()) == "pick one"


async def test_menuscreen_dispatches_the_pressed_item_id(make_app):
    app = make_app(_MenuProbe)
    async with app.run_test() as pilot:
        await pilot.click("#a")
        await pilot.pause()
        assert app.screen.selected == "a"


async def test_menuscreen_marks_a_disabled_item(make_app):
    app = make_app(_MenuProbe)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.query_one("#b", Button).disabled is True


async def test_screen_auto_focuses_nothing_on_open(make_app):
    """AUTO_FOCUS="" — no option looks pre-selected until the player navigates."""
    app = make_app(_MenuProbe)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.focused is None


# --- ChoiceModal / dialog helpers ----------------------------------------------


class _ConfirmProbe(EngineScreen):
    answer: bool | None = None

    def compose(self) -> ComposeResult:
        yield Static("root", id="root")

    def on_mount(self) -> None:
        self._ask()

    @work
    async def _ask(self) -> None:
        self.answer = await self.confirm("sure?", title="Q")


class _ChooseProbe(EngineScreen):
    picked: str | None = None

    def compose(self) -> ComposeResult:
        yield Static("root", id="root")

    def on_mount(self) -> None:
        self._ask()

    @work
    async def _ask(self) -> None:
        self.picked = await self.choose("pick", [("A", "a"), ("B", "b")], title="P")


async def test_confirm_resolves_true_on_the_yes_button(make_app):
    app = make_app(_ConfirmProbe)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, ChoiceModal)  # dialog is raised
        await pilot.click("#opt-0")  # "Yes"
        await pilot.pause()
        assert app.screen.answer is True


async def test_confirm_resolves_false_on_the_no_button(make_app):
    app = make_app(_ConfirmProbe)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#opt-1")  # "No"
        await pilot.pause()
        assert app.screen.answer is False


async def test_choose_resolves_with_the_option_value(make_app):
    app = make_app(_ChooseProbe)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#opt-1")  # second option -> "b"
        await pilot.pause()
        assert app.screen.picked == "b"


# --- Save picker: corrupt-save handling ----------------------------------------


async def test_loading_a_slot_with_corrupt_payload_toasts_and_stays(make_app):
    """Meta reads fine (slot lists) but the payload is garbage — load flags it and doesn't crash."""
    app = make_app(_Blank)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.ctx.state = app.ctx.game.state_cls()  # the fake game's state (from conftest)
        app.ctx.saves.save(0, app.ctx.state, app.ctx.rng, title="doomed")
        with sqlite3.connect(app.ctx.data_dir / "saves.db") as conn:
            conn.execute("UPDATE saves SET payload = 'not json' WHERE slot = 0")

        app.push_screen(SaveSlotScreen("load", next_screen=_Blank))
        await pilot.pause()
        await pilot.click("#slot-0")
        await pilot.pause()

        assert isinstance(app.screen, SaveSlotScreen)  # stayed on the picker, no crash
        assert any("unreadable" in n.message.lower() for n in app._notifications)


async def test_the_load_picker_offers_a_delete_button_per_occupied_slot(make_app):
    app = make_app(_Blank)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.ctx.state = app.ctx.game.state_cls()
        app.ctx.saves.save(0, app.ctx.state, app.ctx.rng, title="run one")

        app.push_screen(SaveSlotScreen("load", next_screen=_Blank))
        await pilot.pause()
        assert app.screen.query_one("#del-0", Button)  # occupied slot got its ✕
        assert not app.screen.query("#del-1")  # the empty slot did not


async def test_the_save_picker_offers_no_delete_buttons(make_app):
    """Saving happens mid-game; a stray click there must not be able to destroy a run."""
    app = make_app(_Blank)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.ctx.state = app.ctx.game.state_cls()
        app.ctx.saves.save(0, app.ctx.state, app.ctx.rng, title="run one")

        app.push_screen(SaveSlotScreen("save"))
        await pilot.pause()
        assert not app.screen.query(".menu-action")


async def test_confirming_the_delete_button_frees_the_slot(make_app):
    app = make_app(_Blank)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.ctx.state = app.ctx.game.state_cls()
        app.ctx.saves.save(0, app.ctx.state, app.ctx.rng, title="run one")

        app.push_screen(SaveSlotScreen("load", next_screen=_Blank))
        await pilot.pause()
        await pilot.click("#del-0")
        await pilot.pause()
        await pilot.click("#opt-0")  # "Yes, delete it"
        await pilot.pause()

        assert app.ctx.saves.exists(0) is False


async def test_declining_the_delete_keeps_the_save(make_app):
    app = make_app(_Blank)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.ctx.state = app.ctx.game.state_cls()
        app.ctx.saves.save(0, app.ctx.state, app.ctx.rng, title="run one")

        app.push_screen(SaveSlotScreen("load", next_screen=_Blank))
        await pilot.pause()
        await pilot.click("#del-0")
        await pilot.pause()
        await pilot.click("#opt-1")  # "Keep it"
        await pilot.pause()

        assert app.ctx.saves.exists(0) is True


# --- min-size overlay ----------------------------------------------------------


async def test_the_min_size_check_survives_an_empty_screen_stack(make_app):
    """`on_resize` arms a 0.15s timer. Quitting inside that window used to land the callback on a
    torn-down app, where `self.screen` raises ScreenStackError."""
    app = make_app(_Blank, min_size=(10, 10))
    async with app.run_test(size=(40, 20)) as pilot:
        await pilot.pause()

    assert not app.screen_stack  # the app is down
    app._enforce_min_size()  # the late timer callback: must be a no-op, not a crash


async def test_leaving_the_app_disarms_the_resize_timer(make_app):
    app = make_app(_Blank, min_size=(10, 10))
    async with app.run_test(size=(40, 20)) as pilot:
        await pilot.pause()
        assert app._resize_timer is not None  # the boot resize armed it

    assert app._resize_timer is None
