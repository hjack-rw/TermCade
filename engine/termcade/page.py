"""Everything the served PAGE is made of: its CSS, its scripts, and the fonts it declares.

Each function answers "what goes in the page", and :mod:`termcade.serve` decides where to put it.
That split is why this module is testable by reading its output, and it is most of the reason
`serve.py` stopped being two files' worth of one.

The browser features the game needs all live here: the auto-fit that sizes the terminal to the
window, the meta channel the app talks to the page through, the WebAudio bridge, the touch
gestures, the arcade Back button, and the font declarations that reach xterm without patching it.

**The CSS and JavaScript are in ``web/``, not in this file.** They used to be written out as Python
string literals, which meant no editor knew any of it was JavaScript: nothing checked a bracket,
nothing coloured a keyword, and every value Python had to supply arrived as an f-string brace in a
language made of braces. What stays here is the part that is genuinely a decision — which grid to
fit, which keycode the Back button sends, which faces are declared and over what range — while
:mod:`termcade.asset` does the reading and the filling in. The docstrings stay here too: they are
about *why the page needs this at all*, which is a question about the game, not about the script.
"""

from __future__ import annotations

from pathlib import Path

from termcade import asset

# Two embedded faces, because one does not cover the game. 0xProto gives xterm.js its text face and
# the card icons; the symbol face is a subset of DejaVu Sans Mono carrying exactly the glyphs 0xProto
# lacks, so no codepoint is claimed twice. Order is load-bearing: 0xProto keeps the text face
# consistent, and DejaVu is only ever reached for what it is missing.
ASSETS = Path(__file__).resolve().parent / "assets"
FONT = ASSETS / "0xProtoNerdFont-Regular.ttf"
SYMBOL_FONT = ASSETS / "TermCadeSymbols.ttf"
FAMILY = "TermCade Mono"
SYMBOL_FAMILY = "TermCade Symbols"

# The cabinet's own icon, already carrying every size a browser picks from (16 through 256). Without
# it a tab shows the browser's blank page glyph, and a game saved to a phone's home screen — which
# is how a tester actually returns to it — gets a screenshot of the page instead of an icon.
ICON = ASSETS / "termcade.ico"
STOCK_STACK = '"Roboto Mono", menlo, monospace'  # the page's own CSS: intro dialog and buttons

# The stack xterm.js actually draws the game with. It is hardcoded in textual.js where the terminal
# is constructed, NOT in the page's CSS, so patching the template alone left every glyph coming from
# Roboto Mono and whatever the browser fell back to for the rest. A desktop hides that (Segoe UI
# Symbol covers the icons); a phone has no such fallback and renders emoji or nothing.
TERM_STACK = "'Roboto Mono', Monaco, 'Courier New', monospace"

# Exactly what TermCadeSymbols.ttf contains, as a CSS `unicode-range`. Both faces are declared under
# the stack's FIRST name, and this is what stops the subset — declared last — claiming the whole
# family and starving every glyph it lacks. See `shadowed_faces` for why the second name is not an
# option.
#
# Generated, never hand-edited: `test_the_symbol_range_matches_the_font` re-derives it from the file
# with fontTools (a test dependency, deliberately not a runtime one — the engine must not need a
# font parser to serve a page) and fails if the subset is rebuilt without refreshing this.
SYMBOL_RANGE = (
    "U+00A0-00FF, U+2000-200A, U+2010-2017, U+201A-201B, U+201E-2023, U+2026, U+202F-2037, "
    "U+2039-203A, U+203C-203F, U+2045-2049, U+204B, U+205F, U+2070-2071, U+2074-208E, U+2090-209C, "
    "U+2190-2211, U+2213, U+2215, U+2217-2220, U+2223, U+2227-222D, U+2234-223D, U+2241-2269, "
    "U+226D-228B, U+228D-22A5, U+22B2-22B5, U+22B8, U+22C2-22C6, U+22CD-22D1, U+22DA-22E9, U+22EF, "
    "U+2300-2306, U+2308-2315, U+2318-2319, U+231C-2321, U+2325-2328, U+232B, U+2335-237A, U+237D, "
    "U+2380-2383, U+2388-238B, U+2395, U+239B-23AE, U+23CE-23CF, U+25A0-262E, U+2639-2653, "
    "U+2655-2664, U+2666-268B, U+2690-269C, U+26A0, U+26B0-26B1, U+2701-2704, U+2706-2709, "
    "U+270C-2727, U+2729-272A, U+272C-274B, U+274D, U+274F-2752, U+2756, U+2758-275E, U+2761-276B, "
    "U+2772-2775, U+2794, U+2798-27AF, U+27B1-27BE, U+27DC"
)

# The two things we match in upstream's TEMPLATE. Both are hand-written HTML, which is the whole
# point: they change when a person edits the page, not when a bundler re-minifies it. Matching
# inside `textual.js` — which is what we used to do — meant any upstream rebuild could silently
# take the game's glyphs away.
GOOGLE_FONTS = '<link\n      rel="stylesheet"\n      href="https://fonts.googleapis.com/css?family=Roboto%20Mono"\n    />'
TERMINAL_SCRIPT = '<script src="{{ config.static.url }}js/textual.js"></script>'

# What the page's Back button sends. Must agree with ``EngineScreen.BACK_KEY``, which is the app's
# side of the same contract — a test pins the two together rather than an import, so the server does
# not have to load the UI to serve a page.
#
# The modifier is load-bearing. xterm.js encodes no function key above F12, so the first attempt
# (F24, chosen because no keyboard has one) produced a button that hid itself and sent nothing.
# Shift+F5 goes down the wire as ``\x1b[15;2~``; a real browser treats it as a reload and never
# delivers it to the page, so the button remains its only source.
BACK_KEY, BACK_CODE, BACK_KEYCODE = "F5", "F5", 116
# Held as NAMES, not as the JavaScript that expresses them. This was ``"shiftKey:true,"`` — a
# fragment of one language kept in a constant of another, spliced into the middle of an object
# literal. It read fine and it was the single thing stopping ``back-button.js`` from being valid
# JavaScript: a parser sees a property with no comma after it and gives up, so no linter could ever
# have checked the file that decides whether the Back button works at all.
BACK_MODIFIERS = ("shift",)
# Every modifier ``KeyboardEvent`` takes, so the template names each one and Python answers true or
# false. A flag the button does not hold is stated rather than omitted — an absent property and a
# false one mean the same thing to the browser, but only one of them can be read off the page.
MODIFIER_KEYS = ("shift", "ctrl", "alt", "meta")

# Without this a phone lays the page out for an imaginary ~980px desktop and then scales the result
# down, so the auto-fit sizes the font against a width the device does not have and everything
# arrives shrunk. It goes in *before* the auto-fit script, which reads `window.innerWidth`.
VIEWPORT = (
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
)

# An xterm cell measures about this much per px of font size. These were briefly made pessimistic to
# force the whole grid inside a phone's viewport — and the result was a font nobody could read. A
# player would rather scroll a legible board than squint at one that fits, and the way OUT of a
# screen no longer depends on the fit: it is a page-level button (see `back_overlay`).
#
# 0.62 is 0xProto's advance, and it is an ESTIMATE — good enough to pick a font size, not good enough
# to lay anything out from. xterm rounds the cell to whole DEVICE pixels, so what a CSS pixel is
# worth depends on the display: at font 8 the cell is 4px on a plain screen and about 4.96px at 3x,
# where a third of a CSS pixel is still a real one. A width computed from this constant was 20% out
# on a 3x phone, which is how a cap meant to hand the game 110 columns handed it 88 — below the
# layout's own breakpoint, so the panels stacked and the state row truncated. Nothing sizes an
# element from this any more; the browser measures its own cells and the fit addon reads them.
CELL_W, CELL_H = 0.62, 1.25
# The floor used to be 8, which is where a phone broke: fitting the game's 44 rows into a landscape
# viewport needs 7px, and clamping back up to 8 made the grid 50px taller than the screen — the page
# loaded overflowing and had to be pinched and scrolled. The floor only ever applies when even
# the smallest fit fails; landscape still resolves to 7, portrait to 5.
MIN_FONT, MAX_FONT = 8, 28

# Fallbacks when no game descriptor is on hand (``serve.main`` under Docker); override via env.
DEFAULT_FIT_SIZE = (110, 38)
# No floor by default: a game whose screens scroll needs no "too small" overlay. Games that really
# cannot reflow pass their own ``min_size``.
DEFAULT_MIN_SIZE: tuple[int, int] | None = None


def autofit(fit_size: tuple[int, int], touch_fit_size: tuple[int, int] | None = None) -> str:
    """Runs first, in ``<head>``: pick the largest xterm font that fits the game's grid in this
    window, and reload with ``?fontsize=N`` when that is not the size already in the URL.

    **Every load re-fits.** It used to run only when the parameter was ABSENT, which sounds like the
    same thing and is not: the parameter is written into the URL, and the URL is what a phone keeps.
    Bookmark it, add it to the home screen, press back, reopen the tab — the fit is skipped, because
    the answer it wrote the first time is still sitting in the query string. A player who first
    opened the game upright was then held at that size in landscape forever, and no amount of
    reloading could recover, since reloading is exactly what carried the stale answer forward.

    A touch device fits a DIFFERENT grid when the cartridge offers one. A phone is short — 312px of
    height against a laptop's 800 — so fitting the desktop's row count means shrinking the font until
    it is unreadable. Asking for fewer rows there gives a legible font instead, and the screens that
    want the space scroll inside their own panel.

    The reload costs a session, so it must not be able to happen twice for one shape. The viewport it
    last replaced for is remembered, and a disagreement it has already acted on is left alone —
    otherwise a browser whose reported height changes as its chrome slides away could bounce between
    two sizes forever, reloading the game each time.
    """
    cols, rows = fit_size
    t_cols, t_rows = touch_fit_size or fit_size
    return asset.script(
        "autofit.js",
        cols=cols,
        rows=rows,
        touch_cols=t_cols,
        touch_rows=t_rows,
        cell_w=CELL_W,
        cell_h=CELL_H,
        min_font=MIN_FONT,
        max_font=MAX_FONT,
    )


def refit_on_rotate() -> str:
    """Make the terminal re-fit when a phone is turned.

    ``textual.js`` fits the grid from ``window.onresize`` and nothing else. A desktop window drag
    fires that continuously, so it has always looked fine — but a phone rotating fires
    ``orientationchange``, and the ``resize`` that follows it arrives while the browser is still
    settling the new viewport. The fit then measures the OLD dimensions and keeps them, which is why
    turning the phone did nothing until the page was reloaded.

    Kicked several times over a second rather than once: there is no event for "the viewport has
    finished changing", and iOS in particular reports intermediate sizes mid-rotation. Re-fitting an
    already-correct grid costs nothing, so the cheap answer is to ask more than once.
    """
    return asset.script("refit-on-rotate.js")


def centre() -> str:
    """Put the terminal in the middle of the window.

    Upstream's page styles the terminal for opacity and nothing else, so the grid sits at the
    document's top-left against the default body margin. On a desktop the window is usually bigger
    than the grid and the game ends up hugging one corner; on a phone the leftover is a visible
    band down one side. Flexing the body centres it on both axes with no effect on the terminal's
    own size — the auto-fit still decides that.

    ``overflow: auto``, not ``hidden``: a font large enough to read makes the grid taller than a
    phone, and hiding the overflow made the bottom rows unreachable rather than merely off-screen.
    The way out of a screen does not depend on this — that button is fixed to the viewport.

    ``safe`` is load-bearing. Plain centring of something TALLER than the window splits the overflow
    across both edges: a device reported the terminal starting 24px above the top of the screen, so
    the first row and the last were both cut. ``safe`` falls back to start-alignment when it does not
    fit, which loses rows only at the end — and nothing at all once it does fit.

    **The terminal is bounded by the WINDOW, in ``dvh``.** Left free it sizes to the screen, and a
    phone's screen is not what a phone shows you: measured on a Samsung, the browser's own chrome
    took 48px of a 360px screen sideways and 174px of 800px upright, and the terminal came out 360px
    tall in a 312px window and 723px in a 626px one. That difference was the scrollbar, in both
    orientations. ``vh`` cannot fix it — on mobile ``vh`` means the screen too, which is the whole
    trap. ``dvh`` tracks the viewport that is actually there, including as the chrome slides away.
    """
    return asset.style("centre.css")


def back_overlay() -> str:
    """A Back button that belongs to the PAGE, not to the terminal.

    A readable font makes the grid taller than a phone's viewport — that is the player's choice, not
    a bug — so the page scrolls. Anything drawn inside the grid scrolls with it, which is why a
    Textual widget in the corner kept ending up somewhere unreachable. Fixed to the viewport it stays
    under the thumb at any font, zoom or scroll position.

    It sends ``EngineScreen.BACK_KEY``, NOT Escape. Escape means whatever the screen it lands on says
    it means, and on the game's hub that is "abandon this run for the main menu" — so a tap that beat
    the button's own hiding used to do exactly that. The key it sends now has one meaning, and the
    app re-checks whether going back is allowed at the moment it arrives.

    The button also hides itself the instant it is tapped, until the app says otherwise. That is not
    the guard — the guard is in the app — but it stops a fast finger queueing presses down a channel
    whose answer is a round trip away.
    """
    return (
        asset.style("back-button.css")
        + "<button id='tc-back-fab' type='button' aria-label='Back' hidden>"
        "<span class='tc-glyph'>&#9664;</span><span class='tc-label'>BACK</span></button>"
        + asset.script(
            "back-button.js",
            back_key=BACK_KEY,
            back_code=BACK_CODE,
            back_keycode=BACK_KEYCODE,
            **{name: str(name in BACK_MODIFIERS).lower() for name in MODIFIER_KEYS},
        )
    )


def meta_signal() -> str:
    """Listen, in the HEAD, for everything the app says to the page.

    Must be installed before ``textual.js`` opens its websocket — wrapping the constructor after the
    socket exists is too late. What each message *means* is not decided here: a packet is handed to
    whatever registered for its type in ``window.__tcMeta``, so the Back button and the speaker each
    own their own behaviour and neither has to know the other exists.
    """
    return asset.script("meta-signal.js")


def audio_bridge() -> str:
    """Play the game's sound in the browser, from samples the app sends down the meta channel.

    The game generates its own audio, so there is nothing to fetch and no asset to serve: raw PCM
    arrives in base64 chunks, is assembled into an ``AudioBuffer`` once, and is kept under the id
    the app gave it. The app never sends the same sound twice, which is why the cache is not
    optional — a music toggle replays what is already here.

    Mixing is the browser's: two sources on one destination sum, so an effect lands over the music
    exactly as the engine's own Mixer does it at a terminal.

    Nothing can play before a gesture. Every browser refuses audio to a page the player has not
    touched, and a phone refuses hardest — so the context is only *created* on the first tap or
    keypress, and a loop that arrived before then is remembered and started at that moment instead
    of being dropped. Without that the soundtrack, which starts on mount, would be lost every time.
    """
    return asset.script("audio-bridge.js")


def no_virtual_keyboard() -> str:
    """Stop a phone throwing its on-screen keyboard up on every tap.

    xterm.js keeps a hidden textarea focused to receive keystrokes, and focusing a textarea is what
    tells a mobile browser to open the keyboard — so every tap on the board covered half the screen
    with keys nobody typed on. ``inputmode="none"`` keeps the focus (and with it paste and IME) while
    telling the browser not to offer the keyboard. Desktop browsers ignore it: they have real keys.

    The textarea is created by xterm.js after this runs, and again whenever the terminal is rebuilt,
    so an observer sets the attribute rather than a one-off query.
    """
    return asset.script("no-virtual-keyboard.js")


def touch_gestures() -> str:
    """Turn finger drags into the events the app already understands: wheels down, arrows across.

    xterm.js reports mouse buttons and wheels; a touch drag is neither, so the Rules book and the
    Game Log simply would not move. A VERTICAL drag becomes `wheel` events on the terminal, which
    xterm forwards to the app as scrolling.

    A HORIZONTAL drag sends Left or Right. The Lore book is the reason — it is paged, and turning
    pages by hunting for a button is a poor way to read on a phone — and it already binds those keys
    for a reader at a terminal, so the swipe asks for the same thing the keyboard does rather than
    inventing a second way to say it. The page follows the finger: swiping left (dragging the page
    away leftwards) is Right, the next page. Nothing else in the game binds the arrows, so a stray
    swipe elsewhere at worst moves the focus ring.

    The 24px travel threshold is not cosmetic. xterm turns a wheel into an ESC-prefixed sequence,
    and Textual reads a stray ESC as the Escape key — so a tap that wobbled a couple of pixels sent
    Escape, and on the temple that means leaving for the main menu. A gesture has to be a real drag
    before any of this fires.

    A swipe fires ONCE per gesture, and only when it is clearly sideways — a finger travelling twice
    as far across as down. Otherwise a diagonal scroll would turn pages while the reader was trying
    to move down one.
    """
    return asset.script("touch-gestures.js")


def min_px(min_size: tuple[int, int]) -> tuple[int, int]:
    """The window below which even the smallest font can't fit the game's floor grid."""
    cols, rows = min_size
    return round(cols * CELL_W * MIN_FONT), round(rows * CELL_H * MIN_FONT)


def faces() -> tuple[tuple[str, Path], ...]:
    """The embedded faces, in the order the terminal should consult them."""
    return ((FAMILY, FONT), (SYMBOL_FAMILY, SYMBOL_FONT))


def favicon() -> str:
    """Point the tab, and a phone's home screen, at the cabinet's icon."""
    if not ICON.exists():
        return ""
    return (
        f"<link rel='icon' href='/static/{ICON.name}'>"
        f"<link rel='apple-touch-icon' href='/static/{ICON.name}'>"
    )


def font_face(family: str, path: Path) -> str:
    """Point at the font as a *file*, not a 2.4MB base64 blob inlined in the page.

    Inlined, the whole HTML document carried the font: mobile browsers never finished it, fell back
    to a system face, and the glyphs the game draws with went missing. Served from /static it
    streams, caches, and does not block the page."""
    return (
        f"@font-face{{font-family:'{family}';src:url('/static/{path.name}') format('truetype');"
        "font-display:block;}"
    )


def deferred_terminal_script() -> str:
    """Load ``textual.js`` only once the fonts are in, by replacing upstream's own script tag.

    xterm measures the cell and bakes a WebGL texture atlas the moment the terminal is constructed,
    so a font that finishes loading afterwards is never drawn with however correct the stack is by
    then. We used to solve that by rewriting the bundle's ``window.onload``; holding the *script*
    back does the same job from the page, and the tag is upstream's own hand-written HTML.

    Degrades rather than blocks. A browser without ``document.fonts``, a font that 404s, a request
    that hangs — every path still ends in the terminal being loaded, because a game in the stock
    font beats a game that never starts. The Jinja expression is left intact: this replacement
    happens outside our ``{% raw %}`` block so the URL is still filled in by the template engine.
    """
    families = ", ".join(f"document.fonts.load(\"16px '{family}'\")" for family, _ in faces())
    return asset.script("deferred-terminal.js", families=families)


def shadowed_faces() -> str:
    """Declare our fonts UNDER THE NAME the terminal already asks for.

    This is what lets us stop rewriting ``textual.js``. xterm is constructed with a hardcoded stack
    — ``TERM_STACK`` — and we used to reach into the minified bundle to put our families in front
    of it. A minified expression changes shape on any upstream rebuild, which made a routine version
    bump able to silently take the game's glyphs away.

    A name, on the other hand, is a contract. Declaring ``Roboto Mono`` to mean our files resolves
    the stack xterm already asks for, with no patch and nothing to match on. The Google Fonts link
    that would otherwise claim the same name is stripped from the page (see ``_templates_dir``) —
    with it present the two declarations both answer, and ordinary letters could come from either.

    **Both files answer to the FIRST name in the stack, and the subset carries a ``unicode-range``.**
    Two faces of one family do not combine their coverage on their own: CSS picks a single face per
    family, so declared bare the subset won ``Roboto Mono`` outright and every glyph only 0xProto has
    — `♔`, `☯`, the box drawing — fell out of the family to whatever the device owned. The range is
    what makes the pair behave as one face: each is asked only for what it holds.

    Declaring the subset as the stack's SECOND name instead looks tidier and does not work. A stack
    falls through family by family for an ordinary glyph, but a codepoint the browser considers
    emoji-capable — `⚙` is `Emoji=Yes` — is routed to the colour emoji font ahead of any later family
    in the stack. So `⚙` never reached the subset and came back as an emoji, which is the exact bug
    the embedded fonts exist to prevent. The first family has to cover everything.

    ``SYMBOL_RANGE`` is generated from the file, not typed out — see the test that re-derives it.
    """
    ranges = {SYMBOL_FONT: f"unicode-range:{SYMBOL_RANGE};"}
    return "".join(
        f"@font-face{{font-family:'Roboto Mono';src:url('/static/{path.name}') "
        f"format('truetype');font-display:block;{ranges.get(path, '')}}}"
        for _, path in faces()
    )


def too_small_gate(min_size: tuple[int, int]) -> tuple[str, str]:
    """A CSS overlay for a game that cannot reflow below ``min_size``. Empty for one that scrolls."""
    min_w, min_h = min_px(min_size)
    style = asset.style("too-small.css", max_w=min_w - 1, max_h=min_h - 1)
    return style, '<div id="tc-toosmall">Window too small &mdash; make it bigger to play.</div>'


def head(
    fit_size: tuple[int, int],
    min_size: tuple[int, int] | None,
    touch_fit_size: tuple[int, int] | None = None,
) -> str:
    """Everything that goes in ``<head>``, in the order it has to run.

    The auto-fit is FIRST because it may reload the page, and doing that after the rest has been
    parsed wastes the work. The meta signal must be installed before ``textual.js`` opens its
    websocket, which is the whole reason it is here rather than at the end of the body.
    """
    gate, _ = too_small_gate(min_size) if min_size is not None else ("", "")
    return (
        VIEWPORT
        + autofit(fit_size, touch_fit_size)
        + meta_signal()
        + audio_bridge()
        + refit_on_rotate()
        + no_virtual_keyboard()
        + touch_gestures()
        + centre()
        + favicon()
        + "<style>"
        + "".join(font_face(family, path) for family, path in faces())
        + shadowed_faces()
        + "</style>"
        + gate
    )


def body(min_size: tuple[int, int] | None) -> str:
    """Everything that goes at the end of ``<body>`` — the parts that need the DOM to exist."""
    _, div = too_small_gate(min_size) if min_size is not None else ("", "")
    return div + back_overlay()
