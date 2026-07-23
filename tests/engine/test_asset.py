"""The page's CSS and JavaScript are files now, which is a new way for the page to arrive empty.

A string literal cannot fail to be there. A file can: left out of the wheel, renamed, or read with
a placeholder nobody filled in. None of those raise anywhere near the browser — they show up as a
game that loads and then quietly does less than it used to, which is precisely the failure the old
concatenated strings could not have.
"""

from __future__ import annotations

import pytest

from termcade import asset, beta, page

_FIT = (110, 38)


def test_every_asset_ships_inside_the_package() -> None:
    """``web/`` sits under ``termcade/`` for the same reason the fonts do: hatch puts the package
    directory in the wheel, so the assets travel with the code that reads them rather than being a
    second thing a Dockerfile has to remember to copy."""
    from pathlib import Path

    import termcade

    assert asset.WEB.is_dir()
    assert asset.WEB.parent == Path(termcade.__file__).resolve().parent
    assert asset._ASSETS, "no assets were discovered under web/"


def test_a_missing_file_is_loud() -> None:
    """The packaging failure, made to raise where it happens. Answering with an empty string here
    would serve a page whose scripts are simply absent, and nothing downstream would notice."""
    with pytest.raises(OSError):
        asset.read("no-such-file.js")


def test_two_assets_with_the_same_name_are_refused(tmp_path) -> None:
    """The folders order the directory, but a caller still names a bare file — so the same name in
    two folders would make the lookup a coin toss. Caught at index time, not at the coin toss."""
    (tmp_path / "css").mkdir()
    (tmp_path / "js").mkdir()
    (tmp_path / "css" / "shared.txt").write_text("one", encoding="utf-8")
    (tmp_path / "js" / "shared.txt").write_text("two", encoding="utf-8")

    with pytest.raises(ValueError, match="share the name"):
        asset._index(tmp_path)


def test_a_placeholder_nobody_filled_in_is_loud() -> None:
    """A rename that stopped halfway would otherwise put the word ``$cols`` in the page."""
    with pytest.raises(KeyError):
        asset.read("autofit.js", cols=110)


def test_a_call_that_lost_its_last_value_is_loud_too() -> None:
    """The hole the test above could not see. It passes one value, so it only ever exercised the
    branch where there was something to substitute — and the shortcut that skipped substitution
    entirely for the empty case turned this exact call into a silent success that served the literal
    ``${max_w}`` into a media query."""
    with pytest.raises(KeyError):
        asset.read("too-small.css")


@pytest.mark.parametrize("name", sorted(asset._ASSETS))
def test_no_asset_sends_its_comments_to_the_browser(name: str) -> None:
    """These blocks are inlined into ``<head>`` on every load, uncached, so prose in them is prose
    paid for on every page view. The files are commented heavily on purpose — that is the whole
    point of them being files — and none of it may reach the wire."""
    body = asset._strip(asset._ASSETS[name].read_text(encoding="utf-8"), name)
    assert body.strip(), f"{name} is empty once its comments are gone"
    assert "//" not in body.replace("://", "")
    assert "/*" not in body
    assert "<!--" not in body


def test_a_comment_that_does_not_own_its_line_is_refused() -> None:
    """The silent-deletion trap. ``/* note */ display: flex;`` opens a comment and does not end in
    the closer, so the old rule armed the block and dropped every line after it until one happened
    to end in ``*/`` — losing real CSS with no error and no failing test. A file that will not load
    is a far better answer than a page missing rules nobody can account for."""
    with pytest.raises(ValueError, match="own its whole line"):
        asset._strip("/* note */ display: flex;\ncolor: red;\n", "made-up.css")


def test_a_comment_that_does_own_its_line_still_works() -> None:
    """The other half — the refusal must not catch the form every asset actually uses."""
    assert asset._strip("/* just a note */\ncolor: red;\n") == "color: red;"
    assert asset._strip("/* opens\n   and closes */\ncolor: red;\n") == "color: red;"


def test_the_page_carries_something_from_every_asset() -> None:
    """The end-to-end version of the packaging check: a marker from each file, in the page the
    server actually hands out. A file that stopped being read would leave its feature gone and every
    other assertion about the page still green."""
    html = page.head(_FIT, (80, 36), None) + page.body((80, 36))
    markers = {
        "autofit.js": "location.replace",
        "refit-on-rotate.js": "orientationchange",
        "meta-signal.js": "window.WebSocket",
        "audio-bridge.js": "AudioContext",
        "no-virtual-keyboard.js": "inputmode",
        "touch-gestures.js": "WheelEvent",
        "back-button.js": "termcade_back",
        "back-button.css": "tc-back-fab",
        "centre.css": "100dvh",
        "too-small.css": "tc-toosmall",
    }
    missing = [name for name, marker in markers.items() if marker not in html]
    assert not missing, f"nothing in the page came from: {', '.join(missing)}"


def test_the_markers_would_notice_an_asset_going_missing() -> None:
    """Guards the test above against being vacuous — a marker that is a substring of the page
    regardless of the file it came from proves nothing."""
    stock = page.head(_FIT, None, None)
    assert "tc-toosmall" not in stock, "the gate's marker is in the page even without the gate"


def test_the_beta_door_still_says_which_way_it_went() -> None:
    """The gate's page is a file too, and it is the one page a locked-out tester ever sees."""
    assert "not on the list" in beta._login_page(bad=True)
    assert "closed beta" in beta._login_page(bad=False)
    assert "<form" in beta._login_page(bad=False)
