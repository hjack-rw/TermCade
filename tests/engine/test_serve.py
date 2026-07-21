"""The browser-serve patch: bundled fonts, auto-fit sized to the game, and the too-small gate."""

from __future__ import annotations

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


def test_the_bundled_fonts_cover_every_character_the_games_draw() -> None:
    """0xProto alone is missing 14 of them — the dashes, the bullet, the arrows, the gear. Those
    used to fall through to the browser, which on a phone means an emoji face or a blank box."""
    from fontTools.ttLib import TTFont

    covered: set[int] = set()
    for _, path in serve._faces():
        covered |= set(TTFont(path).getBestCmap())
    drawn = {
        ord(ch)
        for path in (Path(__file__).resolve().parents[2] / "games").rglob("*.py")
        for ch in path.read_text(encoding="utf-8")
        if ord(ch) > 0x2000 and ch != "︎"  # a variation selector is never itself drawn
    }
    assert not drawn - covered, "no bundled face covers: " + " ".join(
        f"U+{cp:04X}" for cp in sorted(drawn - covered)
    )


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
    statics = serve._statics_dir(tuple(p for _, p in serve._faces()))
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
