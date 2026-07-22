"""Read the page's CSS and JavaScript from files, and fill in what Python has to decide.

The page used to be built out of concatenated string literals — eight ``<script>`` blocks and four
``<style>`` blocks, written as Python source, with no editor able to tell that any of it was
JavaScript. Nothing checked a bracket, nothing coloured a keyword, and a typo showed up as a browser
that quietly did less than it used to.

Now each block is a real ``.js`` or ``.css`` file under ``web/``, and this module is the whole of
the machinery that gets it into the page.

**``$name``, not ``{name}``.** Every other line of CSS and JavaScript is a brace, so ``str.format``
would mean doubling almost all of them — which is how a template gets harder to read than the string
it replaced. ``string.Template`` uses a sigil neither language spends, and it *raises* on a
placeholder nobody supplied, so a renamed value fails at import rather than serving a page with the
word ``$cols`` in it.

**The comments do not go to the browser.** These blocks are inlined into ``<head>`` on every load,
uncached, so prose in them is prose paid for on every page view. A comment on its own line is
dropped on the way out; that is the only form allowed, and it is why nothing here tries to parse
JavaScript to find one.
"""

from __future__ import annotations

from pathlib import Path
from string import Template

WEB = Path(__file__).resolve().parent / "web"


def read(name: str, /, **values: object) -> str:
    """The contents of ``web/name``, with ``$placeholders`` filled in and comments stripped.

    Raises rather than papering over either half: a missing file is a packaging bug (the wheel
    shipped a page with no scripts), and a missing value is a rename that has not finished.
    """
    body = _strip((WEB / name).read_text(encoding="utf-8"), name)
    # Always substituted, even with nothing to substitute. Skipping the call when ``values`` is
    # empty looks like a harmless shortcut and quietly repeals the guarantee above: a caller that
    # loses its last keyword argument stops raising and starts serving the literal text
    # ``${max_w}`` into a media query, which is a broken breakpoint no test would see.
    return Template(body).substitute(values)


def script(name: str, /, **values: object) -> str:
    """``web/name`` as a ``<script>`` block, ready to go in the page."""
    return f"<script>{read(name, **values)}</script>"


def style(name: str, /, **values: object) -> str:
    """``web/name`` as a ``<style>`` block, ready to go in the page."""
    return f"<style>{read(name, **values)}</style>"


def _strip(source: str, name_hint: str = "<source>") -> str:
    """Drop blank lines and whole-line comments, and join what is left with newlines.

    Deliberately not a minifier and deliberately not a parser. It looks at whole lines only, so a
    ``//`` inside a string literal is safe by construction — a comment shares its line with nothing,
    which is a rule the files keep rather than one this function enforces.

    A CSS ``/* */`` or an HTML ``<!-- -->`` may run over several lines, because a comment worth
    writing rarely fits on one and neither language has a ``//``. It still has to own every line it
    touches: the opener starts a line and the closer ends one. A line that does both and then
    carries on is refused outright — it used to arm the block and silently drop everything after it,
    and code deleted without a word is a worse answer than a file that will not load.

    Line structure and indentation survive; only blank lines and comments go. That is what keeps
    the page legible in a browser's devtools — the place anyone debugging it is actually standing —
    and it means a file that is valid JavaScript is still valid JavaScript on the way out, rather
    than depending on this function to have rejoined it correctly.
    """
    openers = {"/*": "*/", "<!--": "-->"}
    kept: list[str] = []
    closer: str | None = None
    for line in source.splitlines():
        stripped = line.strip()
        if closer is not None:
            if stripped.endswith(closer):
                closer = None
            continue
        if not stripped or stripped.startswith("//"):
            continue
        opened = next((o for o in openers if stripped.startswith(o)), None)
        if opened is not None:
            end = openers[opened]
            if stripped.endswith(end):
                continue
            # A line that opens a comment, closes it, and then carries on is the trap: it would arm
            # the block and silently delete every line after it until something happened to end in
            # `*/`. Deleting code without a word is worse than refusing the file, so refuse it.
            if end in stripped[len(opened) :]:
                raise ValueError(
                    f"{name_hint}: a comment must own its whole line — {stripped!r} closes one and "
                    "then keeps going, which would swallow the code that follows it"
                )
            closer = end
            continue
        kept.append(line.rstrip())
    return "\n".join(kept)
