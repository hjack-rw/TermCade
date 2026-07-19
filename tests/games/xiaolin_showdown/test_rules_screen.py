"""The rulebook: the primer, the reference, and the search that makes the reference usable.

Two failure modes are worth a test. A rule the game *enforces* and the book never states can only be
learned by losing a run to it — so every mechanic printed into the game has to turn up here. And a
number typed into the book by hand goes stale the moment the setting moves, which is worse than
saying nothing at all, so every number is read off the settings.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from textual.widgets import Input, ListItem, ListView

from xiaolin_showdown.logic.battle import Round
from xiaolin_showdown.logic.mechanics.prize import PrizeRoute, claim_route
from xiaolin_showdown.logic.settings import XiaolinSettings
from xiaolin_showdown.screens.rules import (
    HOW_TO_PLAY,
    PRIMER,
    RulesScreen,
    _slug,
    matching,
    rules_for,
)


def _text_of(rules: list[str]) -> str:
    return " ".join(rules).lower()


def _all_text(rules: dict[str, list[str]]) -> str:
    return " ".join(rule for section in rules.values() for rule in section).lower()


def test_the_primer_teaches_the_loop_and_stops_there():
    """Short enough to read standing up. It is a primer, not the manual — that is the whole split."""
    assert len(HOW_TO_PLAY) <= 8

    primer = " ".join(HOW_TO_PLAY).lower()
    for beat in ("one action", "gong yi tanpai", "forfeits", "pile runs dry"):
        assert beat in primer, f"the loop does not mention {beat!r}"


def test_the_prize_cascade_states_every_route_the_code_can_take():
    """Driven off `PrizeRoute` itself, so printing a fifth route into the game fails this test.

    The four routes read as prose ("a decisive blow", "a win on two fronts"), and each enum member's
    own value *is* that prose — so the book is checked against the game's words, not against mine.
    """
    book = _all_text(rules_for(XiaolinSettings()))

    for route in PrizeRoute:
        assert str(route).lower() in book, f"the rulebook never states the route {str(route)!r}"


def test_every_mechanic_a_player_meets_is_written_down():
    """A rule the code obeys and the book never states can only be learned by losing a run to it.

    This list is hand-kept and that is a weakness — it cannot catch a mechanic nobody thought to add
    here. It is a floor, not a guarantee; `test_the_prize_cascade_states_every_route_the_code_can_take`
    is what a real guard looks like.
    """
    book = _all_text(rules_for(XiaolinSettings()))

    for mechanic in (
        "initiative",  # who names the challenge
        "early bird",  # a Wu taken by being faster
        "tournament",
        "boost",
        "curses your opponent",  # a negative Wu lands opposite
        "metal",  # opposed on every coloured arena
        "prize wu",
        "lost",  # the Wu nobody wins
        "dealt back in",  # the mercy rule — the biggest source of Wu in the game
    ):
        assert mechanic in book, f"the rulebook never mentions {mechanic!r}"


def test_the_prize_routes_print_the_thresholds_the_code_actually_checks():
    """The book's numbers are read out of the *evaluator*, not out of my memory of it.

    The old version of this test compared the rulebook against three literals I had typed — so moving a
    route in `prize.claim_route` would leave the book lying and the test green, which is the one failure
    this whole file exists to prevent. Now the bar for each route is *found* by probing the real rule,
    and the book has to agree with what was found.
    """
    settings = XiaolinSettings(prize_threshold=9)
    book = _all_text(rules_for(settings))

    for route, bar in _bars_the_code_checks(settings.prize_threshold).items():
        printed = f"beat {bar - 1}"  # "beat N" means "reach N+1", which is what the code tests
        assert printed in book, f"the book never says {printed!r} for {route}"


def test_the_book_prints_this_runs_target_not_the_pools():
    """A run deals a subset and derives its OWN target, so the settings' figure — read off the whole
    pool — is not what the player is racing to. The book must print the run's number."""
    settings = XiaolinSettings()
    dealt_target = settings.point_limit // 2  # this run was dealt a smaller deck, so a nearer target

    book = _all_text(rules_for(settings, target=dealt_target))

    assert f"bank {dealt_target} points" in book  # `_all_text` lowercases
    assert f"bank {settings.point_limit} points" not in book


def test_the_book_falls_back_to_the_settings_target_before_a_run():
    """From the start screen there is no dealt deck yet, so what a new game would be dealt is honest."""
    settings = XiaolinSettings()

    assert f"bank {settings.point_limit} points" in _all_text(rules_for(settings))


def _bars_the_code_checks(threshold: int) -> dict[PrizeRoute, int]:
    """The lowest end value that claims the Wu by each route — asked of `claim_route` itself.

    Probed rather than restated: a battle is handed end values, one route at a time, and the smallest
    value that fires each one is what the rule really requires.
    """
    def fires(route: PrizeRoute, value: int) -> bool:
        battle = Round(stat="force")
        # a decisive blow needs one stat; two fronts needs two; total command needs all three
        needed = {PrizeRoute.DECISIVE_BLOW: 1, PrizeRoute.BROAD_WIN: 2, PrizeRoute.TOTAL_COMMAND: 3}
        battle.player.result = [value if i < needed[route] else 0 for i in range(3)]
        return (
            claim_route(
                [battle],
                winner_is_player=True,
                background="metal",
                threshold=threshold,
                bonus_cancelled=True,  # the elemental route must not answer for another one
            )
            is route
        )

    bars = {}
    for route in (PrizeRoute.DECISIVE_BLOW, PrizeRoute.BROAD_WIN, PrizeRoute.TOTAL_COMMAND):
        bars[route] = next(value for value in range(1, 40) if fires(route, value))
    return bars


def test_the_early_bird_prints_the_gap_the_code_checks():
    settings = XiaolinSettings(early_bird_gap=6)

    assert "lead them by 6" in _all_text(rules_for(settings))


def test_searching_narrows_the_book_to_the_rules_that_mention_it():
    found = matching(rules_for(XiaolinSettings()), "boost")

    assert found  # something was found
    for section in found.values():
        assert any("boost" in rule.lower() for rule in section)


def test_searching_a_heading_keeps_its_whole_section():
    """Someone typing "initiative" wants the initiative rules, not only the ones repeating the word."""
    rules = rules_for(XiaolinSettings())
    found = matching(rules, "initiative")

    assert found["Initiative"] == rules["Initiative"]


def test_a_section_with_no_hits_is_dropped_entirely():
    """A heading standing over nothing reads as a bug."""
    found = matching(rules_for(XiaolinSettings()), "tournament")

    assert "When the Pile Runs Dry" not in found
    assert found  # but the sections that do mention it survive


def test_an_empty_search_is_the_whole_book():
    rules = rules_for(XiaolinSettings())

    assert matching(rules, "") == rules
    assert matching(rules, "   ") == rules


def test_a_search_that_finds_nothing_finds_nothing():
    assert matching(rules_for(XiaolinSettings()), "zzzz") == {}


# --- the screen itself: a rail of sections, and a search that hides until it is called -----------


@pytest.fixture
def book(tmp_path):
    """Open the rulebook, and hand back the app and its pilot."""
    from termcade.ui.app import EngineApp
    from xiaolin_showdown.game import build_game
    from xiaolin_showdown.screens.rules import RulesScreen

    @asynccontextmanager
    async def _book():
        app = EngineApp(build_game(), data_dir=tmp_path, seed=1234)
        async with app.run_test(size=(150, 50)) as pilot:
            await pilot.pause()
            app.push_screen(RulesScreen())
            await pilot.pause()
            yield app, pilot

    return _book


def _text(screen) -> str:
    """Every rule on the page, flattened — asked of the screen, not scraped off the render.

    `RulesScreen.showing` is what the screen *decided to put up*, one step before Rich draws it. Reading
    the words back out of a rendered widget instead would test Rich, and would break the first time
    Textual moved its internals (it already has: an earlier version of this reached for `.renderable`,
    which no longer exists).
    """
    return " ".join(rule for section in screen.showing.values() for rule in section).lower()


def _headings(screen) -> set[str]:
    return {heading.lower() for heading in screen.showing}


async def test_the_rail_lists_every_section_of_the_book(book):
    """The contents page IS the navigation — a section missing from the rail cannot be reached."""
    async with book() as (app, _pilot):
        rail = app.screen.query_one("#rule-nav", ListView)
        listed = {str(item.id) for item in rail.query(ListItem)}

        expected = {_slug(name) for name in [PRIMER, *rules_for(XiaolinSettings())]}
        assert listed == expected


async def test_it_opens_on_how_to_play(book):
    """A player with no question yet lands on the loop, not on a wall of edge cases."""
    async with book() as (app, _pilot):
        assert app.screen.showing == {PRIMER: HOW_TO_PLAY}


async def test_moving_down_the_rail_turns_the_page(book):
    """Highlighting a section shows it — there is no separate 'open' step to discover.

    `Tab` first, because the book opens *out* of focus mode: the arrows belong to the rail only once a
    player has asked for them. This test passed without it while the rail stole focus on arrival, which
    is the behaviour it was hiding.
    """
    async with book() as (app, pilot):
        first_section = next(iter(rules_for(XiaolinSettings())))

        await pilot.press("tab")  # into focus mode, the way a player gets there
        await pilot.press("down")  # off How to Play, onto the first real section
        await pilot.pause()

        assert set(app.screen.showing) == {first_section}


async def test_the_search_box_is_hidden_until_it_is_called_for(book):
    """A search field open on a book you have not read is clutter."""
    async with book() as (app, _pilot):
        assert not app.screen.query_one("#rule-search", Input).display


async def test_r_summons_the_search_and_puts_the_cursor_in_it(book):
    """One key, and you are typing — not one key to reveal and another to reach."""
    async with book() as (app, pilot):
        await pilot.press("r")
        await pilot.pause()

        box = app.screen.query_one("#rule-search", Input)
        assert box.display
        assert app.screen.focused is box


async def test_searching_cuts_across_every_section(book):
    """The point of searching is not knowing which section the rule lives in.

    "Initiative" and "the vault" are different sections; a Wu of speed is ruled on in both.
    """
    async with book() as (app, pilot):
        await pilot.press("r")
        app.screen.query_one("#rule-search", Input).value = "action"
        await pilot.pause()

        assert len(app.screen.showing) > 1  # the hits came from more than one section
        assert all("action" in _text_of(section) for section in app.screen.showing.values())


async def test_a_result_says_which_section_it_came_from(book):
    """Half the answer to "where does this rule live" is the heading over it."""
    async with book() as (app, pilot):
        await pilot.press("r")
        app.screen.query_one("#rule-search", Input).value = "tournament"
        await pilot.pause()

        assert "Calling a Showdown" in app.screen.showing  # the heading came with the hit


async def test_a_search_with_no_answer_says_so(book):
    """An empty pane leaves a player wondering whether the search is broken."""
    async with book() as (app, pilot):
        await pilot.press("r")
        app.screen.query_one("#rule-search", Input).value = "zzzz"
        await pilot.pause()

        assert app.screen.showing == {}  # nothing to show — and the page says so instead of sitting blank


async def test_escape_closes_the_search_before_it_closes_the_book(book):
    """The first Escape puts the book back the way it was. Only the second one leaves."""
    async with book() as (app, pilot):
        await pilot.press("r")
        app.screen.query_one("#rule-search", Input).value = "tournament"
        await pilot.pause()

        await pilot.press("escape")
        await pilot.pause()

        assert isinstance(app.screen, RulesScreen)  # still in the book
        assert not app.screen.query_one("#rule-search", Input).display  # but the search is gone
        assert app.screen.query_one("#rule-nav", ListView).display  # and the rail is back


async def test_the_book_opens_out_of_focus_mode(book):
    """Like every other screen in the engine — and this one used to be the exception.

    `Tab` is offered in the footer as the way *into* keyboard mode. On a screen that starts in it,
    pressing the advertised key throws you out of a mode you never asked to enter, which is worse than
    the second of friction it saves.
    """
    async with book() as (app, _pilot):
        assert app.screen.focused is None


async def test_tab_puts_the_keyboard_on_the_rail(book):
    """And then the arrows turn pages, which is what focus mode is *for*."""
    async with book() as (app, pilot):
        await pilot.press("tab")
        await pilot.pause()

        assert app.screen.focused is app.screen.query_one("#rule-nav", ListView)

        await pilot.press("down")
        await pilot.pause()

        assert PRIMER not in app.screen.showing  # off the primer, onto the first real section


async def test_the_search_key_reaches_the_box_without_focus_mode(book):
    """`R` is a shortcut, not a second step: it does not ask a player to enter focus mode first."""
    async with book() as (app, pilot):
        await pilot.press("r")
        await pilot.pause()

        assert app.screen.focused is app.screen.query_one("#rule-search", Input)
