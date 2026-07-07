"""XS menu loop on the engine (headless Pilot): start, character select, and save/load."""

from __future__ import annotations

from termcade.ui.app import EngineApp

from textual.widgets import Input

from xiaolin_showdown.game import build_game
from xiaolin_showdown.screens.character_select import CharacterSelectScreen
from xiaolin_showdown.screens.rules import RulesScreen
from xiaolin_showdown.screens.start import StartScreen
from xiaolin_showdown.screens.vault import VaultScreen


async def test_boots_to_start_screen(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, StartScreen)


async def test_rules_screen_opens_from_the_menu(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test() as pilot:
        await pilot.click("#rules")
        await pilot.pause()
        assert isinstance(app.screen, RulesScreen)


async def test_play_selects_a_character_then_deals_into_the_vault(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test() as pilot:
        await pilot.click("#play")
        await pilot.pause()
        assert isinstance(app.screen, CharacterSelectScreen)

        await pilot.click("#char-1")  # Omi
        await pilot.pause()
        assert isinstance(app.screen, VaultScreen)
        assert app.ctx is not None
        assert app.ctx.state is not None
        assert app.ctx.state.player.character.name == "Omi"


async def test_save_then_continue_restores_the_hand(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test() as pilot:
        await pilot.click("#play")
        await pilot.pause()
        await pilot.click("#char-1")  # Omi -> vault
        await pilot.pause()
        saved_hand = [card.id for card in app.ctx.state.player.hand]

        await pilot.press("s")  # vault Save action -> slot picker
        await pilot.pause()
        await pilot.click("#slot-0")  # save, back to vault
        await pilot.pause()
        assert isinstance(app.screen, VaultScreen)

        await pilot.press("escape")  # vault -> start
        await pilot.pause()
        assert isinstance(app.screen, StartScreen)

        await pilot.click("#continue")  # -> load slot picker
        await pilot.pause()
        await pilot.click("#slot-0")  # load, -> vault
        await pilot.pause()
        assert isinstance(app.screen, VaultScreen)
        assert [card.id for card in app.ctx.state.player.hand] == saved_hand


async def test_settings_change_flows_into_a_new_game(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test() as pilot:
        await pilot.click("#settings")
        await pilot.pause()
        app.screen.query_one("#set-starting_hand_player", Input).value = "3"
        await pilot.click("#save")  # persists, back to start
        await pilot.pause()

        await pilot.click("#play")
        await pilot.pause()
        await pilot.click("#char-1")  # Omi (has one inalienable card)
        await pilot.pause()
        assert len(app.ctx.state.player.hand) == 2  # 3 dealt minus the inalienable card
