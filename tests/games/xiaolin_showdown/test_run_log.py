"""What the Game Log must catch in a real run.

The engine logs every toast on its own (see `tests/engine/ui/test_game_log.py`). These are about the
things the *cartridge* owes it: the two actions that change the game and raise **no** toast — a Wu
banked, a showdown settled — and the Wu in a line of prose, which only the game knows how to draw.
"""

from __future__ import annotations

from termcade.ui.screens.dialog import ChoiceModal
from termcade.ui.screens.log import GameLogScreen

from xiaolin_showdown.logic.constants import TOURNAMENT
from xiaolin_showdown.logic.duel import DuelState
from xiaolin_showdown.logic.mechanics.powers import is_gamble, trigger_of
from xiaolin_showdown.logic.mechanics.prize import PrizeRoute
from xiaolin_showdown.logic.turn import DEPOSIT
from xiaolin_showdown.screens.duel import DuelScreen, _showdown_story
from xiaolin_showdown.screens.format import (
    OPPONENT_LOG,
    SHOWDOWN_LOG,
    display_name,
    opponent_move,
    stats_line,
    wu_in_prose,
    your_move,
)
from xiaolin_showdown.screens.vault import VaultScreen


def _log(app) -> str:
    return "\n".join(entry.message for entry in app.ctx.journal.entries)


def _plain(catalog):
    """A Wu worth points, with no power the deposit would stop to ask about forfeiting."""
    return next(
        card
        for card in catalog.cards
        if card.points > 0 and trigger_of(card.power) != "use" and not is_gamble(card.power)
    )


async def test_the_vault_opens_the_log(open_vault, state):
    async with open_vault(state) as (app, pilot):
        await pilot.press("7")
        await pilot.pause()

        assert isinstance(app.screen, GameLogScreen)


async def test_a_drawn_wu_reaches_the_log(open_vault, state, card):
    """The toast path, end to end in the real game: what the vault says, the log keeps."""
    state.player.deck.append(card(6))
    wanted = state.player.deck[-1].name

    async with open_vault(state) as (app, pilot):
        await pilot.press("2")  # Draw
        await pilot.pause()

        assert wanted in _log(app)


async def test_a_banked_wu_reaches_the_log(open_vault, state, catalog, card):
    """A deposit raises no toast — you watch the points move — so the log has to be told."""
    banked = card(_plain(catalog).id)
    # Two Wu, because a deposit may not empty a hand — the one being banked is `#dep-0`.
    state.player.hand = [banked, card(_plain(catalog).id)]

    async with open_vault(state) as (app, pilot):
        await pilot.press("3")  # Deposit
        await pilot.pause()
        await pilot.click("#dep-0")
        await pilot.pause()

        assert isinstance(app.screen, VaultScreen)
        # Read off the card, never restated — a re-cost must not need this test edited.
        assert f"{banked.name} for {banked.points} pts" in _log(app)


async def test_your_move_is_filed_as_yours(open_vault, state, catalog, card):
    """Whose move it was is the first thing the log has to say — "Deposit" alone leaves it to be
    worked out from the sentence underneath."""
    state.player.hand = [card(_plain(catalog).id), card(_plain(catalog).id)]

    async with open_vault(state) as (app, pilot):
        await pilot.press("3")  # Deposit
        await pilot.pause()
        await pilot.click("#dep-0")
        await pilot.pause()

        titles = [entry.title for entry in app.ctx.journal.entries]
        assert your_move(DEPOSIT) in titles


async def test_the_showdown_closes_the_turn_it_was_fought_in(open_vault, state):
    """A showdown is the END of a turn, not the start of the next.

    You spend your action, they spend theirs, and then you fight — so the result is the last line of
    that turn. What comes after it is the next turn opening, and their move opens it.
    """
    async with open_vault(state) as (app, pilot):
        await pilot.press("1")  # Gong Yi Tanpai
        for _ in range(300):  # drive the stepped showdown: continue, take the first option offered
            await pilot.pause()
            if isinstance(app.screen, ChoiceModal):
                await pilot.click("#opt-0")
            elif isinstance(app.screen, DuelScreen):
                await pilot.press("space")
            else:
                break

        entries = app.ctx.journal.entries
        showdown = next(entry for entry in entries if entry.title == SHOWDOWN_LOG)
        after = [entry for entry in entries if entry.turn > showdown.turn]

        assert showdown.turn == 1, "the showdown belongs to the turn that was played, not the next one"
        assert after, "the turn after it is empty"
        assert after[0].title.startswith(OPPONENT_LOG), "their move opens the turn after it"


def test_a_stat_challenge_names_the_price_and_who_named_it(state, catalog):
    """You set the terms, I set the price — so the duelist who did NOT call the challenge is the one
    who asks for a 2v2. A tournament prices itself, and says nothing."""
    duel = DuelState(
        stakes=catalog.card(6),
        challenge="force",
        background="water",
        background_name="Snowy Slope",
        wager=2,
        player_priority=True,  # the PLAYER called it, so the opponent names the price
        winner=True,
        winner_character=state.player.character.name,
        prize_route=PrizeRoute.DECISIVE_BLOW,
    )

    story = _showdown_story(duel, state).plain

    opponent = display_name(state.bot.character.name)
    assert f"{opponent} requested a {duel.wager}v{duel.wager}!" in story
    assert "Snowy Slope" in story  # the place, not the element it was summoned under


def test_a_tournament_asks_nobody_for_a_price(state, catalog):
    duel = DuelState(
        stakes=catalog.card(6),
        challenge=TOURNAMENT,
        background="water",
        background_name="Snowy Slope",
        wager=1,
        player_priority=True,
    )

    assert "requested" not in _showdown_story(duel, state).plain


def test_both_sides_file_the_same_action_under_the_same_word():
    """One shape, two sides. A move of theirs titled differently from the same move of yours makes a
    reader compare shapes instead of sides."""
    assert your_move(DEPOSIT) == "Your move: Deposit"
    assert opponent_move([DEPOSIT]) == "Opponent's move: Deposit"


def test_a_wu_named_in_prose_is_drawn_as_a_wu(catalog):
    """The log's lines are sentences the game wrote. A card in one of them is still a card.

    Everywhere else a Wu is an element-coloured name and its stats; the log is not the one screen
    where it comes out as plain grey words.
    """
    wu = next(card for card in catalog.cards if card.name)

    drawn = wu_in_prose(f"Katnappe played {wu.name}")

    assert drawn.plain == f"Katnappe played {wu.name} ({stats_line(wu.stats)})"
    assert drawn.spans, "the Wu was written as plain text — it must carry its element's colour"
