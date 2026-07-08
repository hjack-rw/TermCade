"""The browser-serve font patch embeds the bundled font and puts it first in the terminal stack."""

from __future__ import annotations

import jinja2

from termcade import serve


def test_font_asset_is_bundled() -> None:
    assert serve._FONT.exists(), "the browser font must ship inside the package"


def test_patched_template_is_valid_jinja() -> None:
    # aiohttp_jinja2 renders this page as a Jinja2 template, so the injected CSS/JS/base64 must not
    # contain anything Jinja2 reads as a tag (e.g. `{#`) — otherwise the browser gets a 500.
    templates = serve._templates_dir()
    assert templates is not None
    html = (templates / "app_index.html").read_text(encoding="utf-8")
    jinja2.Environment().from_string(html)  # raises TemplateSyntaxError if a brace is misread


def test_serve_embeds_font_first_in_the_stack() -> None:
    templates = serve._templates_dir()
    assert templates is not None  # the stock template was found and patched
    html = (templates / "app_index.html").read_text(encoding="utf-8")
    assert "@font-face" in html
    assert "data:font/ttf;base64," in html
    # our font leads the terminal font stack, ahead of textual-serve's stock fonts
    assert f'"{serve._FAMILY}", {serve._STOCK_STACK}' in html
    # the auto-fit script sizes the xterm font to the window (via a ?fontsize reload)
    assert "fontsize" in html and "location.replace" in html
    # the minimum-window gate is present, keyed to the target pixel size
    assert "tc-toosmall" in html
    assert str(serve._MIN_PX[0]) in html and str(serve._MIN_PX[1]) in html
