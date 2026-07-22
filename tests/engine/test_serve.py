"""The browser-serve patch: bundled fonts, auto-fit sized to the game, and the too-small gate."""

from __future__ import annotations

import re
from pathlib import Path

import jinja2

from termcade import serve

_FIT = (110, 38)
_MIN = (80, 36)


def _html(fit=_FIT, minimum=None) -> str:
    templates = serve._templates_dir(fit, minimum)
    assert templates is not None  # the stock template was found and patched
    return (templates / "app_index.html").read_text(encoding="utf-8")


def test_font_assets_are_bundled() -> None:
    for family, path in serve._faces():
        assert path.exists(), f"{family} must ship inside the package"


def _covered() -> set[int]:
    from fontTools.ttLib import TTFont

    covered: set[int] = set()
    for _, path in serve._faces():
        covered |= set(TTFont(path).getBestCmap())
    return covered


def _drawn() -> set[int]:
    """Every non-ASCII character the games put on screen.

    The card icons are NOT found by reading the source: they are written as ``\\U0001f580`` escapes
    so the files stay ASCII, so a scan for literal characters sees backslashes and passes on an
    empty set — which is exactly what this test used to do while reporting green. They are imported
    from the game instead, which is the only way to read what it actually draws.
    """
    from xiaolin_showdown.screens.format import ICONS

    literal = {
        ord(ch)
        for path in (Path(__file__).resolve().parents[2] / "games").rglob("*.py")
        for ch in path.read_text(encoding="utf-8")
        if ord(ch) > 0x2000
    }
    icons = {ord(ch) for icon in ICONS.values() for ch in icon}
    return {cp for cp in literal | icons if cp != 0xFE0E}  # a selector is never itself drawn


def test_the_bundled_fonts_cover_every_character_the_games_draw() -> None:
    """The whole point of bundling two faces. Anything neither covers falls through to the browser,
    which on a phone means an emoji face or a blank box."""
    missing = _drawn() - _covered()
    assert not missing, "no bundled face covers: " + " ".join(
        f"U+{cp:04X}" for cp in sorted(missing)
    )


def test_the_cover_check_actually_sees_the_card_icons() -> None:
    """Guards the test above against the bug it used to have — a source scan finds no icon at all,
    so the check passed on an empty set while every icon went unverified."""
    from xiaolin_showdown.screens.format import ICONS

    assert ord("\U0001f580") in _drawn(), "the icons are escaped in source and must be imported"
    assert len([icon for icon in ICONS.values() if icon]) >= 8


def test_patched_template_is_valid_jinja() -> None:
    # aiohttp_jinja2 renders this page as a Jinja2 template, so the injected CSS/JS/base64 must not
    # contain anything Jinja2 reads as a tag (e.g. `{#`) — otherwise the browser gets a 500.
    jinja2.Environment().from_string(_html())  # raises TemplateSyntaxError if a brace is misread


def test_serve_declares_every_bundled_font() -> None:
    html = _html()
    for _, path in serve._faces():
        # Served as a file, not inlined: a 2.4MB base64 blob in the page never finished loading on
        # a phone, so the browser fell back to a system face and the game's glyphs went missing.
        assert f"/static/{path.name}" in html
    assert html.count("@font-face") == len(serve._faces())
    assert "base64" not in html


def _statics() -> Path:
    statics = serve._statics_dir(tuple(p for _, p in serve._faces()) + (serve._ICON,))
    assert statics is not None
    return statics


def test_the_terminal_itself_draws_with_our_fonts() -> None:
    """The page's CSS stack is not the one xterm draws with — that one is built in textual.js, so a
    template-only patch left the game rendering in Roboto Mono and the browser's own fallback."""
    ours = "".join(f"'{family}', " for family, _ in serve._faces())
    assert ours + serve._TERM_STACK in (_statics() / "js" / "textual.js").read_text(encoding="utf-8")


def test_the_text_face_is_consulted_before_the_symbol_face() -> None:
    """The symbol face only fills gaps; leading with it would change how ordinary text looks."""
    js = (_statics() / "js" / "textual.js").read_text(encoding="utf-8")
    assert js.index(f"'{serve._FAMILY}'") < js.index(f"'{serve._SYMBOL_FAMILY}'")


def test_the_terminal_waits_for_the_fonts_before_it_measures() -> None:
    """xterm bakes a texture atlas at construction, so a font that arrives later is never used."""
    js = (_statics() / "js" / "textual.js").read_text(encoding="utf-8")
    assert "document.fonts.ready" in js
    assert js.index("document.fonts.ready") < js.index('querySelectorAll(".textual-terminal")')


def test_the_font_files_sit_where_the_page_asks_for_them() -> None:
    statics = _statics()
    for _, path in serve._faces():
        assert (statics / path.name).exists()


def test_a_sideways_swipe_turns_a_page() -> None:
    """The Lore book is paged and already binds the arrows, so the swipe asks for the same thing the
    keyboard does. The page follows the finger: swiping left is the NEXT page."""
    html = _html()
    assert "ArrowRight" in html and "ArrowLeft" in html
    assert html.index("ax<0") < html.index("ArrowRight")


def test_a_swipe_fires_once_and_only_when_clearly_sideways() -> None:
    """A diagonal scroll must not turn pages while the reader is moving down one."""
    html = _html()
    assert "swiped=true" in html
    assert "Math.abs(ny-y)*2" in html  # twice as far across as down


def test_a_vertical_drag_still_scrolls() -> None:
    html = _html()
    assert "WheelEvent" in html


def test_the_tab_wears_the_cabinets_icon() -> None:
    """A tester returns to a beta build by tapping it on a home screen — without this that tile is
    a screenshot of the page."""
    html = _html()
    assert f"/static/{serve._ICON.name}" in html
    assert "apple-touch-icon" in html


def test_the_icon_is_actually_served() -> None:
    statics = _statics()
    assert (statics / serve._ICON.name).exists()


def test_the_back_button_sends_the_key_the_app_listens_for() -> None:
    """Two halves of one contract, held apart on purpose: the server must not import the UI just to
    serve a page. This is what keeps them honest."""
    from termcade.ui.screens.base import EngineScreen

    modifiers = "".join(part[: -len("Key:true,")] for part in [serve._BACK_MODIFIER])
    assert EngineScreen.BACK_KEY == f"{modifiers}+{serve._BACK_KEY}".lower()


def test_the_back_button_does_not_send_escape() -> None:
    """Escape is a key each screen gives its own meaning — on the game's hub it abandons the run.
    A button whose only guard is hiding itself must never carry it."""
    html = _html()
    assert "'Escape'" not in html and "keyCode:27" not in html


def test_the_back_key_is_one_xterm_actually_encodes() -> None:
    """The gap every other Back-button test missed.

    F24 was chosen first because no keyboard has one — and xterm.js has no case for any function key
    above F12, so the button hid itself on tap and sent nothing at all. Every Python test still
    passed: they press the key straight into Textual and never cross the terminal. This one reads the
    encoding table out of the bundle we actually ship.
    """
    js = (_statics() / "js" / "textual.js").read_text(encoding="utf-8")
    assert f"case {serve._BACK_KEYCODE}:" in js, (
        f"xterm.js cannot encode keyCode {serve._BACK_KEYCODE} — the Back button would be silent"
    )


def test_the_back_key_carries_its_modifier_down_the_wire() -> None:
    """The modifier is not decoration: it is what distinguishes this from a bare F5 reload. xterm
    only emits the modified form from the `a?` branch of that key's case."""
    js = (_statics() / "js" / "textual.js").read_text(encoding="utf-8")
    assert re.search(rf"case {serve._BACK_KEYCODE}:o\.key=a\?", js), (
        "xterm encodes this key with no modifier branch, so shift is dropped on the way out"
    )


def test_the_back_button_carries_a_modifier() -> None:
    """xterm.js encodes no function key above F12 — a bare exotic key is dropped on the floor and
    the button goes silently dead. The modifier is what puts it on the wire."""
    assert "Key:true" in serve._BACK_MODIFIER
    assert serve._BACK_MODIFIER in _html()


def test_the_back_button_is_for_devices_with_no_keys() -> None:
    """A desktop browser has Escape and a footer that says so, which makes a moulded plastic button
    over the terminal pure decoration. Hidden by default, so a browser that cannot answer the media
    query gets the keyboard's UI rather than a control it does not need."""
    html = _html()
    assert "@media (pointer: coarse)" in html
    fab = html[html.index("#tc-back-fab{position:fixed") :]
    assert fab.index("#tc-back-fab{display:none}") < fab.index("@media (pointer: coarse)")


def test_the_back_button_hides_itself_the_moment_it_is_tapped() -> None:
    """Not the guard — that is in the app — but it stops a fast finger queueing presses down a
    channel whose answer is a round trip away."""
    html = _html()
    back = html[html.index("<button id='tc-back-fab'") :]
    assert "b.hidden=true" in back[: back.index("</script>")]


def test_the_page_can_play_the_games_sound() -> None:
    html = _html()
    assert "AudioContext" in html and "createBuffer" in html


def test_sound_waits_for_a_gesture_the_browser_will_accept() -> None:
    """No browser lets a page nobody has touched make noise, and the soundtrack starts on mount —
    so a tune arriving before the first tap has to be held, not dropped."""
    html = _html()
    assert "pointerdown" in html and "pending" in html


def test_every_message_from_the_app_goes_through_one_registry() -> None:
    """The Back button and the speaker both listen; neither should know the other exists."""
    html = _html()
    assert "__tcMeta" in html
    for meta_type in ("termcade_back", "termcade_audio"):
        assert f"__tcMeta['{meta_type}']" in html


def test_the_socket_is_wrapped_before_textual_opens_it() -> None:
    """Wrapping the constructor after the socket exists is too late — every message is missed."""
    html = _html()
    assert html.index("window.WebSocket=") < html.index("</head>")


def test_the_page_tells_a_phone_its_real_width() -> None:
    """Without this a phone lays out for an imaginary ~980px desktop and scales the result down, so
    the auto-fit measures a width the device does not have and the game arrives shrunk."""
    html = _html()
    assert 'name="viewport"' in html and "width=device-width" in html


def test_the_viewport_is_declared_before_the_autofit_reads_it() -> None:
    """The auto-fit script reads `window.innerWidth`, so the meta must be parsed first."""
    html = _html()
    assert html.index('name="viewport"') < html.index("innerWidth")


def test_a_tap_does_not_raise_the_phones_keyboard() -> None:
    """xterm.js keeps a hidden textarea focused, and a focused textarea is what opens the on-screen
    keyboard — so every tap on the board buried the game under keys nobody typed on."""
    html = _html()
    assert "xterm-helper-textarea" in html and "'inputmode','none'" in html


def test_the_keyboard_suppressor_survives_the_terminal_being_rebuilt() -> None:
    """The textarea does not exist when the page loads, and is remade with the terminal."""
    assert "MutationObserver" in _html()


def test_autofit_sizes_the_font_to_the_games_fit_size() -> None:
    """The page fits the layout the game *wants*, not the floor it merely survives."""
    html = _html(fit=(110, 38))
    assert "fontsize" in html and "location.replace" in html
    assert "c=touch?110:110" in html and "r=touch?38:38" in html


def test_a_game_with_a_min_size_gets_a_too_small_gate() -> None:
    min_w, min_h = serve._min_px(_MIN)
    html = _html(minimum=_MIN)
    assert "tc-toosmall" in html
    assert f"max-width:{min_w - 1}px" in html and f"max-height:{min_h - 1}px" in html


def test_a_game_without_a_min_size_gets_no_gate() -> None:
    """Screens scroll once they outgrow the window, so zooming in is a choice, not an error."""
    assert "tc-toosmall" not in _html(minimum=None)


def test_autofit_clamps_to_the_readable_font_range() -> None:
    html = _html()
    assert f"Math.max({serve._MIN_FONT}" in html and f"Math.min(a,b,{serve._MAX_FONT})" in html


def test_the_page_ships_no_controls_that_reload_the_session() -> None:
    """A reload starts a *new* textual-serve session, throwing the player's run away. Only the
    auto-fit may navigate, and only before the game starts (when `fontsize` is absent)."""
    html = _html()
    assert "tc-zoom" not in html  # the zoom cluster reloaded on every click
    # The one surviving `location.replace` is the auto-fit, guarded by `if (!p.has('fontsize'))`.
    assert html.count("location.replace") == 1
    assert "if(!p.has('fontsize'))" in html


def test_serve_reads_the_sizes_off_the_game_descriptor(monkeypatch) -> None:
    """Without this the page auto-fits one grid while the game lays out for another."""
    monkeypatch.setenv("GAME_FACTORY", "xiaolin_showdown.game:build_game")
    from xiaolin_showdown.game import build_game

    game = build_game()
    assert serve._descriptor_sizes() == (game.fit_size, game.min_size, game.touch_fit_size)


def test_serve_falls_back_to_engine_defaults_without_a_factory(monkeypatch) -> None:
    monkeypatch.delenv("GAME_FACTORY", raising=False)
    assert serve._descriptor_sizes() == (serve.DEFAULT_FIT_SIZE, serve.DEFAULT_MIN_SIZE, None)


def test_a_phone_is_offered_the_games_own_touch_grid() -> None:
    """A phone fitting the desktop's row count means a font nobody can read — the auto-fit shrinks
    until all 44 rows go in. Fewer rows there, and a legible font follows."""
    templates = serve._templates_dir((110, 44), None, (110, 30))
    assert templates is not None
    html = (templates / "app_index.html").read_text(encoding="utf-8")
    assert "pointer: coarse" in html
    assert "r=touch?30:44" in html
