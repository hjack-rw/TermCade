"""XS menu loop on the engine (headless Pilot): start, character select, and save/load."""

from __future__ import annotations

from copy import deepcopy

from termcade.ui.app import EngineApp

from textual.widgets import Input

from xiaolin_showdown.game import build_game
from xiaolin_showdown.screens.character_select import CharacterSelectScreen
from xiaolin_showdown.screens.detail import DetailScreen
from xiaolin_showdown.screens.duel import ChoiceModal, DuelScreen
from xiaolin_showdown.screens.lookup import LookUpScreen
from xiaolin_showdown.screens.outcome import OutcomeScreen
from xiaolin_showdown.screens.rules import RulesScreen
from xiaolin_showdown.screens.start import StartScreen
from xiaolin_showdown.screens.use_power import UsePowerScreen
from xiaolin_showdown.screens.vault import VaultScreen


async def _new_game_at_vault(app, pilot):
    """Boot → Play → pick Omi → land on the vault."""
    await pilot.click("#play")
    await pilot.pause()
    await pilot.click("#char-1")
    await pilot.pause()


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


async def test_lookup_picks_a_card_and_shows_its_detail(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test() as pilot:
        await _new_game_at_vault(app, pilot)
        await pilot.press("c")  # Look up cards -> pick list
        await pilot.pause()
        assert isinstance(app.screen, LookUpScreen)

        await pilot.click("#look-0")  # pick the first card
        await pilot.pause()
        assert isinstance(app.screen, DetailScreen)


async def test_deposit_banks_a_card_for_points(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test() as pilot:
        await _new_game_at_vault(app, pilot)
        hand_before = len(app.ctx.state.player.hand)
        points_before = app.ctx.state.player.points
        gained = app.ctx.state.player.hand[0].points

        await pilot.press("d")  # Deposit
        await pilot.pause()
        await pilot.click("#dep-0")  # cash the first card, back to the vault
        await pilot.pause()

        assert isinstance(app.screen, VaultScreen)
        assert len(app.ctx.state.player.hand) == hand_before - 1
        assert app.ctx.state.player.points == points_before + gained


async def test_gong_yi_tanpai_plays_a_showdown_and_returns_to_the_vault(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test() as pilot:
        await _new_game_at_vault(app, pilot)
        assert isinstance(app.screen, VaultScreen)

        await pilot.press("g")  # Gong Yi Tanpai — the showdown runs in an async worker
        assert isinstance(app.screen, (DuelScreen, ChoiceModal))

        # Drive the stepped showdown: press Continue on the board, take the first option on any
        # decision dialog. One showdown steps through ~7 phases with three choices in between.
        landed = None
        for _ in range(300):
            await pilot.pause()
            if isinstance(app.screen, ChoiceModal):
                await pilot.click("#opt-0")
            elif isinstance(app.screen, DuelScreen):
                await pilot.press("space")  # advance a phase
            else:
                landed = app.screen
                break

        # One showdown does not exhaust the deck, so control returns to a fresh vault.
        assert isinstance(landed, VaultScreen)
        assert app.ctx.state.card_deck  # the run is not over


async def test_use_a_power_opens_the_picker_and_returns_to_the_vault(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test() as pilot:
        await _new_game_at_vault(app, pilot)
        cat = app.ctx.state.catalog
        bras = deepcopy(next(card for card in cat.cards if card.name == "Bras Finger"))
        app.ctx.state.player.hand.append(bras)  # ensure a usable-power Wu is in hand

        await pilot.press("p")  # Use a Power → picker
        await pilot.pause()
        assert isinstance(app.screen, UsePowerScreen)

        await pilot.click("#pow-0")  # spend the first usable Wu, back to the vault
        await pilot.pause()
        assert isinstance(app.screen, VaultScreen)


async def test_draw_pulls_a_wu_from_the_personal_deck(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test() as pilot:
        await _new_game_at_vault(app, pilot)
        cat = app.ctx.state.catalog
        app.ctx.state.player.deck.append(deepcopy(cat.card(6)))  # a Wu waiting in the personal deck
        hand_before = len(app.ctx.state.player.hand)

        await pilot.press("w")  # Draw a card
        await pilot.pause()

        assert isinstance(app.screen, VaultScreen)  # a fresh vault reflecting the draw
        assert len(app.ctx.state.player.hand) == hand_before + 1
        assert not app.ctx.state.player.deck


async def test_game_over_shows_the_outcome_and_can_play_again(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test() as pilot:
        await _new_game_at_vault(app, pilot)  # a live game state to score
        app.ctx.state.has_ended = True
        app.ctx.state.player.points = 4

        app.push_screen(OutcomeScreen())
        await pilot.pause()
        assert isinstance(app.screen, OutcomeScreen)

        await pilot.click("#again")  # Play Again → pick a new dragon
        await pilot.pause()
        assert isinstance(app.screen, CharacterSelectScreen)


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
