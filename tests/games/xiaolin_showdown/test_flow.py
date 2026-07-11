"""XS menu loop on the engine (headless Pilot): start, character select, and save/load."""

from __future__ import annotations

from copy import deepcopy

from termcade.core.settings import Difficulty
from termcade.ui.app import EngineApp

from textual.widgets import Button, Input, Static

from xiaolin_showdown.game import build_game
from termcade.core.rng import Rng
from xiaolin_showdown.logic.catalog import load_catalog
from xiaolin_showdown.logic.setup import new_game
from xiaolin_showdown.screens.character_select import CharacterSelectScreen
from xiaolin_showdown.screens.detail import DetailScreen
from termcade.ui.screens.dialog import ChoiceModal

from xiaolin_showdown.screens.duel import DuelScreen
from xiaolin_showdown.screens.lookup import LookUpScreen
from xiaolin_showdown.screens.outcome import OutcomeScreen
from xiaolin_showdown.screens.rules import RulesScreen
from xiaolin_showdown.screens.start import StartScreen
from xiaolin_showdown.screens.use_power import UsePowerScreen
from xiaolin_showdown.screens.vault import VaultScreen


async def _boot(app, pilot):
    """Wait for the root screen to land on the stack.

    ``EngineApp.on_mount`` pushes it asynchronously, so an immediate click can race an empty stack
    ("No screens on stack") or hit the attract scene instead.
    """
    for _ in range(50):
        if app.screen_stack and isinstance(app.screen, StartScreen):
            return
        await pilot.pause()
    raise AssertionError("start screen never appeared")


async def _new_game_at_vault(app, pilot):
    """Boot → Play → pick Omi → land on the vault."""
    await _boot(app, pilot)
    await pilot.click("#play")
    await pilot.pause()
    await pilot.click("#char-1")
    await pilot.pause()


async def test_boots_to_start_screen(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _boot(app, pilot)
        await pilot.pause()
        assert isinstance(app.screen, StartScreen)


async def test_rules_screen_opens_from_the_menu(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _boot(app, pilot)
        await pilot.click("#rules")
        await pilot.pause()
        assert isinstance(app.screen, RulesScreen)


async def test_play_selects_a_character_then_deals_into_the_vault(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _boot(app, pilot)
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
    async with app.run_test(size=(150, 60)) as pilot:
        await _boot(app, pilot)
        await pilot.click("#play")
        await pilot.pause()
        await pilot.click("#char-1")  # Omi -> vault
        await pilot.pause()
        saved_hand = [card.id for card in app.ctx.state.player.hand]

        await pilot.press("0")  # vault Save action -> slot picker
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
    async with app.run_test(size=(150, 60)) as pilot:
        await _boot(app, pilot)
        await _new_game_at_vault(app, pilot)
        await pilot.press("5")  # Look up cards -> pick list
        await pilot.pause()
        assert isinstance(app.screen, LookUpScreen)

        await pilot.click("#look-0")  # pick the first card
        await pilot.pause()
        assert isinstance(app.screen, DetailScreen)


async def test_deposit_banks_a_card_for_points(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _boot(app, pilot)
        await _new_game_at_vault(app, pilot)
        hand_before = len(app.ctx.state.player.hand)
        points_before = app.ctx.state.player.points
        gained = app.ctx.state.player.hand[0].points

        await pilot.press("3")  # Deposit
        await pilot.pause()
        await pilot.click("#dep-0")  # cash the first card, back to the vault
        await pilot.pause()

        assert isinstance(app.screen, VaultScreen)
        assert len(app.ctx.state.player.hand) == hand_before - 1
        assert app.ctx.state.player.points == points_before + gained


async def test_gong_yi_tanpai_plays_a_showdown_and_returns_to_the_vault(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _boot(app, pilot)
        await _new_game_at_vault(app, pilot)
        assert isinstance(app.screen, VaultScreen)

        await pilot.press("1")  # Gong Yi Tanpai — the showdown runs in an async worker
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
    async with app.run_test(size=(150, 60)) as pilot:
        await _boot(app, pilot)
        await _new_game_at_vault(app, pilot)
        cat = app.ctx.state.catalog
        bras = deepcopy(next(card for card in cat.cards if card.name == "Bras Finger"))
        app.ctx.state.player.hand.append(bras)  # ensure a usable-power Wu is in hand

        await pilot.press("4")  # Use a Power → picker
        await pilot.pause()
        assert isinstance(app.screen, UsePowerScreen)

        await pilot.click("#pow-0")  # spend the first usable Wu, back to the vault
        await pilot.pause()
        assert isinstance(app.screen, VaultScreen)


async def test_draw_pulls_a_wu_from_the_personal_deck(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _boot(app, pilot)
        await _new_game_at_vault(app, pilot)
        cat = app.ctx.state.catalog
        app.ctx.state.player.deck.append(deepcopy(cat.card(6)))  # a Wu waiting in the personal deck
        hand_before = len(app.ctx.state.player.hand)

        await pilot.press("2")  # Draw a card
        await pilot.pause()

        assert isinstance(app.screen, VaultScreen)  # a fresh vault reflecting the draw
        assert len(app.ctx.state.player.hand) == hand_before + 1
        assert not app.ctx.state.player.deck


async def test_reaching_the_point_limit_ends_the_game_instead_of_dueling(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _boot(app, pilot)
        await _new_game_at_vault(app, pilot)
        app.ctx.state.player.points = 999  # already past the point limit

        await pilot.press("1")  # try Gong Yi Tanpai
        await pilot.pause()

        assert isinstance(app.screen, OutcomeScreen)  # the run ends now, no extra duel


async def test_depositing_a_power_wu_asks_to_confirm_first(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:  # tall enough that every card button is on-screen
        await _new_game_at_vault(app, pilot)
        bras = deepcopy(next(c for c in app.ctx.state.catalog.cards if c.name == "Bras Finger"))
        app.ctx.state.player.hand.append(bras)  # a deposit-power Wu

        await pilot.press("3")  # deposit
        await pilot.pause()
        await pilot.click(f"#dep-{len(app.ctx.state.player.hand) - 1}")  # pick the power Wu
        await pilot.pause()
        assert isinstance(app.screen, ChoiceModal)  # forfeit-the-power confirmation

        await pilot.click("#opt-1")  # "No, keep it"
        await pilot.pause()
        assert any(card is bras for card in app.ctx.state.player.hand)  # kept, not banked


async def test_look_up_can_inspect_the_opponents_cards(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:  # both hands listed — keep every button on-screen
        await _new_game_at_vault(app, pilot)
        await pilot.press("5")  # look up cards
        await pilot.pause()
        assert isinstance(app.screen, LookUpScreen)

        state = app.ctx.state
        last = len(state.player.whole_hand) + len(state.bot.whole_hand) - 1  # the last is an opponent card
        await pilot.click(f"#look-{last}")
        await pilot.pause()
        assert isinstance(app.screen, DetailScreen)  # opponent card detail opens


async def test_game_over_shows_the_outcome_and_can_play_again(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _boot(app, pilot)
        await _new_game_at_vault(app, pilot)  # a live game state to score
        app.ctx.state.has_ended = True
        app.ctx.state.player.points = 4

        app.push_screen(OutcomeScreen())
        await pilot.pause()
        assert isinstance(app.screen, OutcomeScreen)

        await pilot.click("#again")  # Play Again → pick a new dragon
        await pilot.pause()
        assert isinstance(app.screen, CharacterSelectScreen)


async def test_start_screen_shows_the_cartridge_version(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _boot(app, pilot)
        await pilot.pause()
        assert str(app.screen.query_one("#version", Static).render()) == "v1.1"


async def test_settings_flags_an_out_of_range_value_instead_of_saving(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _boot(app, pilot)
        await pilot.click("#settings")
        await pilot.pause()
        settings_screen = app.screen
        app.screen.query_one("#set-max_hand_size", Input).value = "4"  # below the 5-card starting hand
        await pilot.click("#save")
        await pilot.pause()
        assert app.screen is settings_screen  # rejected — stays on settings, doesn't pop
        assert any("Max Hand Size" in n.message for n in app._notifications)  # flagged as a toast


async def test_settings_rejected_value_is_not_persisted(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _boot(app, pilot)
        await pilot.click("#settings")
        await pilot.pause()
        app.screen.query_one("#set-max_hand_size", Input).value = "4"
        await pilot.click("#save")
        await pilot.pause()
        assert app.ctx.settings.current.options["max_hand_size"] == 6  # unchanged default, not saved


async def test_settings_change_flows_into_a_new_game(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _boot(app, pilot)
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


async def test_settings_defaults_to_easy(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _boot(app, pilot)
        await pilot.pause()
        assert app.ctx.settings.current.difficulty is Difficulty.EASY


async def test_the_difficulty_toggle_switches_between_easy_and_hard(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _boot(app, pilot)
        await pilot.click("#settings")
        await pilot.pause()
        # Textual holds a button "-active" for ~0.3s after a press and drops a click landing inside
        # that window, so a back-to-back re-click needs to wait it out.
        await pilot.click("#difficulty")
        await pilot.pause(0.4)
        assert "HARD" in str(app.screen.query_one("#difficulty", Button).label)

        await pilot.click("#difficulty")  # toggles back
        await pilot.pause(0.4)
        assert "EASY" in str(app.screen.query_one("#difficulty", Button).label)


async def test_an_abandoned_settings_screen_does_not_change_difficulty(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _boot(app, pilot)
        await pilot.click("#settings")
        await pilot.pause()
        await pilot.click("#difficulty")  # pick HARD but leave without saving
        await pilot.press("escape")
        await pilot.pause()
        assert app.ctx.settings.current.difficulty is Difficulty.EASY


async def test_saving_hard_difficulty_deals_a_hard_opponent(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _boot(app, pilot)
        await pilot.click("#settings")
        await pilot.pause()
        await pilot.click("#difficulty")
        await pilot.click("#save")  # persists HARD, back to start
        await pilot.pause()
        assert app.ctx.settings.current.difficulty is Difficulty.HARD

        await pilot.click("#play")
        await pilot.pause()
        await pilot.click("#char-1")  # Omi
        await pilot.pause()
        assert app.ctx.state.bot.character.is_hard is True


async def test_a_wide_vault_lays_the_hands_side_by_side(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(120, 40)) as pilot:
        await _boot(app, pilot)
        await _new_game_at_vault(app, pilot)
        rows = {p.region.y for p in app.screen.query("#hands > BoxedPanel")}
        assert len(rows) == 1  # both panels share a row


async def test_a_narrow_vault_stacks_the_hands(tmp_path):
    """Below the engine's `-wide` breakpoint the panels can't sit side by side, so they stack —
    which is what lets a zoomed-in (fewer-cells) board keep playing."""
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(90, 44)) as pilot:
        await _boot(app, pilot)
        await _new_game_at_vault(app, pilot)
        assert app.screen.has_class("-narrow")
        rows = {p.region.y for p in app.screen.query("#hands > BoxedPanel")}
        assert len(rows) == 2  # one panel per row


async def test_a_zoomed_in_board_scrolls_instead_of_gating(tmp_path):
    """Auto-fit sizes the board to the window; zooming past it is the player's choice, so the
    screen scrolls rather than blocking with a "too small" overlay."""
    # Deal the game straight onto the board: at this size the start menu itself needs scrolling,
    # which a player can do but `pilot.click` cannot.
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(85, 20)) as pilot:  # far below the floor this used to gate at
        await pilot.pause()
        catalog = load_catalog()
        app.ctx.state = new_game(catalog, Rng(1234), catalog.character(1))
        app.push_screen(VaultScreen())
        await pilot.pause()
        await pilot.pause()

        assert isinstance(app.screen, VaultScreen)  # no "too small" overlay took over
        assert app.screen.show_vertical_scrollbar
        assert app.screen.max_scroll_y > 0

        app.screen.scroll_end(animate=False)
        await pilot.pause()
        actions = app.screen.query_one("#actions").parent
        assert actions.region.bottom <= 20  # the bottom panel is reachable by scrolling


async def test_the_game_declares_no_size_floor():
    assert build_game().min_size is None


async def test_the_fit_size_covers_the_tallest_screen(tmp_path):
    """Auto-fit sizes the browser font to `fit_size`. If any screen is taller, the game opens
    already scrolled — which is what happened when it was tuned to the vault, not the start menu.
    """
    game = build_game()
    fit_cols, fit_rows = game.fit_size
    app = EngineApp(game, data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(fit_cols, fit_rows)) as pilot:
        await _boot(app, pilot)
        assert not app.screen.show_vertical_scrollbar, "the start menu does not fit the fit_size"
        assert app.screen.virtual_size.height <= fit_rows


# --- a showdown opens with initiative resolved, and commits on the first Continue ---


async def _open_showdown(app, pilot):
    await _boot(app, pilot)
    await pilot.click("#play")
    await pilot.pause()
    await pilot.click("#char-1")
    await pilot.pause()
    await pilot.press("1")  # Gong Yi Tanpai
    await pilot.pause()
    return app.screen


async def test_a_showdown_opens_showing_initiative_before_anything_is_pressed(tmp_path):
    """Initiative is a property of the hands, not a phase to click through."""
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        screen = await _open_showdown(app, pilot)

        assert screen._duel.duel.stage == 0  # nothing has advanced
        assert screen._duel.duel.bot.initiative == 1
        assert screen._duel.duel.player_priority is False  # already known, no coin needed


async def test_the_opening_board_stakes_nothing_so_you_may_retreat(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        screen = await _open_showdown(app, pilot)
        assert screen._duel.duel.stakes is None

        await pilot.press("escape")
        await pilot.pause()

        assert isinstance(app.screen, VaultScreen)


async def test_the_first_continue_draws_the_prize_and_locks_you_in(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _open_showdown(app, pilot)

        await pilot.press("enter")
        await pilot.pause()

        assert app.screen._duel.duel.stakes is not None


async def test_there_is_no_retreat_once_the_showdown_has_begun(tmp_path):
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _open_showdown(app, pilot)
        await pilot.press("enter")
        await pilot.pause()

        await pilot.press("escape")
        await pilot.pause()

        assert isinstance(app.screen, DuelScreen)


async def test_rules_open_from_the_vault(tmp_path):
    """The rules are needed mid-run, not only from the main menu."""
    app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
    async with app.run_test(size=(150, 60)) as pilot:
        await _new_game_at_vault(app, pilot)

        await pilot.press("7")
        await pilot.pause()

        assert isinstance(app.screen, RulesScreen)


async def test_every_vault_action_says_what_it_does(tmp_path):
    """A greyed action shows why; an available one shows what it is for. Neither can be silent."""
    from xiaolin_showdown.screens.vault import _ACTION_HELP, _ACTIONS

    keys = [action.split(".")[0] for action in _ACTIONS]

    assert set(keys) == set(_ACTION_HELP)


def test_the_rulebook_prints_the_numbers_the_game_actually_uses():
    """A rulebook that says 7 while the code checks 8 is worse than no rulebook.

    Every tunable a rule mentions is read from the settings, so changing one number changes both the
    behaviour and the page that explains it.
    """
    from xiaolin_showdown.logic.settings import XiaolinSettings
    from xiaolin_showdown.screens.rules import rules_for

    odd = XiaolinSettings(prize_threshold=99, max_wager=2, point_limit=42)
    text = " ".join(rule for rules in rules_for(odd).values() for rule in rules)

    assert "99" in text  # the prize threshold
    assert "up to 2" in text  # the wager cap
    assert "42 points" in text  # the point limit


def test_the_rulebook_states_every_wager_rule():
    """The wager is the newest rule and the easiest to leave undocumented."""
    from xiaolin_showdown.logic.settings import XiaolinSettings
    from xiaolin_showdown.screens.rules import rules_for

    text = " ".join(rule for rules in rules_for(XiaolinSettings()).values() for rule in rules).lower()

    assert "did not call the challenge" in text  # who names the stakes
    assert "more than they hold" in text  # you cannot demand what they cannot field
    assert "most rounds won" in text  # how a best-of-N is decided
    assert "margin" in text  # ...and how a level match breaks
