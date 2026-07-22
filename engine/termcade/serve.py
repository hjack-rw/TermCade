"""Serve a termcade game to the browser with the bundled full-coverage fonts embedded.

``textual-serve`` renders the game in xterm.js using a webfont that lacks the Unicode symbols
games draw with, so the browser substitutes colour emoji (wrong width, broken alignment). We patch
textual-serve at runtime — serving our fonts from ``/static``, declaring them in the page, and
putting them first in the terminal's font stack — so every glyph renders consistently with no
host-side install. The xterm.js protocol and static assets are used exactly as shipped.

That stack lives in ``textual.js``, not in the page's CSS. Patching the template alone changed the
intro dialog and left the terminal drawing in Roboto Mono, which is why the icons only ever looked
right on machines whose own fallback happened to cover them.

Configured by environment: ``GAME`` (the console command to run), ``PORT``, ``PUBLIC_URL``
(the browser-reachable URL — it must not be ``0.0.0.0`` or the websocket cannot connect back), and
``GAME_FACTORY`` (``pkg.module:callable`` returning the game's ``Game``), so the page's auto-fit
reads the cartridge's own sizes instead of a copy of them. ``TERMCADE_CODES`` additionally puts the
closed-beta gate in front of everything — see :mod:`termcade.beta`.
"""

from __future__ import annotations

import importlib
import os
import shutil
import tempfile
from pathlib import Path

import textual_serve
from textual_serve.server import Server

from termcade import beta
from termcade.session import TermCadeServer

# Two embedded faces, because one does not cover the game. 0xProto gives xterm.js its text face and
# the card / affiliation icons, but it is missing 14 of the 28 non-ASCII characters the game actually
# draws — the en and em dash, the bullet, the ellipsis, the subscript digits, the arrows, and the
# gear and warning signs among them. Those used to fall through to the browser's own fallback, which
# on a desktop quietly lands on a covering system face (Segoe UI Symbol) and on a phone lands on an
# emoji font or on nothing at all. The symbol face is a subset of DejaVu Sans Mono covering the
# punctuation, arrow, technical, box, shape and symbol blocks a TUI draws from, so it fills the gaps
# for characters the game has not used yet as well as the ones it has. Order is load-bearing: 0xProto
# first keeps the text face consistent, and DejaVu is only ever reached for what 0xProto lacks.
_ASSETS = Path(__file__).resolve().parent / "assets"
_FONT = _ASSETS / "0xProtoNerdFont-Regular.ttf"
_SYMBOL_FONT = _ASSETS / "TermCadeSymbols.ttf"
_FAMILY = "TermCade Mono"
_SYMBOL_FAMILY = "TermCade Symbols"

# The cabinet's own icon, already carrying every size a browser picks from (16 through 256). Without
# it a tab shows the browser's blank page glyph, and a game saved to a phone's home screen — which
# is how a tester actually returns to it — gets a screenshot of the page instead of an icon.
_ICON = _ASSETS / "termcade.ico"
_STOCK_STACK = '"Roboto Mono", menlo, monospace'  # the page's own CSS: intro dialog and buttons

# The stack xterm.js actually draws the game with. It is hardcoded in textual.js where the terminal
# is constructed, NOT in the page's CSS, so patching the template alone left every glyph coming from
# Roboto Mono and whatever the browser fell back to for the rest. A desktop hides that (Segoe UI
# Symbol covers the icons); a phone has no such fallback and renders emoji or nothing.
_TERM_STACK = "'Roboto Mono', Monaco, 'Courier New', monospace"

# What the page's Back button sends. Must agree with ``EngineScreen.BACK_KEY``, which is the app's
# side of the same contract — a test pins the two together rather than an import, so the server does
# not have to load the UI to serve a page.
#
# The modifier is load-bearing. xterm.js encodes no function key above F12, so the first attempt
# (F24, chosen because no keyboard has one) produced a button that hid itself and sent nothing.
# Shift+F5 goes down the wire as ``\x1b[15;2~``; a real browser treats it as a reload and never
# delivers it to the page, so the button remains its only source.
_BACK_KEY, _BACK_CODE, _BACK_KEYCODE = "F5", "F5", 116
_BACK_MODIFIER = "shiftKey:true,"
# Where textual.js builds the terminal. We hold it until the font is in, because xterm measures the
# cell and bakes a WebGL texture atlas at construction: a font that lands afterwards is never drawn
# with, however correct the stack is by then.
_ONLOAD = 'window.onload=e=>{const t=document.querySelectorAll(".textual-terminal")'

# Without this a phone lays the page out for an imaginary ~980px desktop and then scales the result
# down, so the auto-fit sizes the font against a width the device does not have and everything
# arrives shrunk. It goes in *before* the auto-fit script, which reads `window.innerWidth`.
_VIEWPORT = (
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
)

# An xterm cell measures about this much per px of font size. These were briefly made pessimistic to
# force the whole grid inside a phone's viewport — and the result was a font nobody could read. A
# player would rather scroll a legible board than squint at one that fits, and the way OUT of a
# screen no longer depends on the fit: it is a page-level button (see `_back_overlay`).
_CELL_W, _CELL_H = 0.60, 1.25
# The floor used to be 8, which is where a phone broke: fitting the game's 44 rows into a landscape
# viewport needs 7px, and clamping back up to 8 made the grid 50px taller than the screen — the page
# loaded overflowing and had to be pinched and scrolled. The floor only ever applies when even
# the smallest fit fails; landscape still resolves to 7, portrait to 5.
_MIN_FONT, _MAX_FONT = 8, 28

# Fallbacks when no game descriptor is on hand (``serve.main`` under Docker); override via env.
DEFAULT_FIT_SIZE = (110, 38)
# No floor by default: a game whose screens scroll needs no "too small" overlay. Games that really
# cannot reflow pass their own ``min_size``.
DEFAULT_MIN_SIZE: tuple[int, int] | None = None


def _autofit(fit_size: tuple[int, int], touch_fit_size: tuple[int, int] | None = None) -> str:
    """Runs first, in ``<head>``: pick the largest xterm font that fits the game's grid in this
    window, then reload once with ``?fontsize=N``. Guarded on the param being absent, so it only ever
    runs before the game starts and never fights a size the player zoomed to.

    A touch device fits a DIFFERENT grid when the cartridge offers one. A phone is short — 312px of
    height against a laptop's 800 — so fitting the desktop's row count means shrinking the font until
    it is unreadable. Asking for fewer rows there gives a legible font instead, and the screens that
    want the space scroll inside their own panel.
    """
    cols, rows = fit_size
    t_cols, t_rows = touch_fit_size or fit_size
    return (
        "<script>(function(){var p=new URLSearchParams(location.search);"
        f"if(!p.has('fontsize')){{var touch=window.matchMedia('(pointer: coarse)').matches;"
        f"var c=touch?{t_cols}:{cols},r=touch?{t_rows}:{rows};"
        f"var a=Math.floor(window.innerWidth/(c*{_CELL_W})),"
        f"b=Math.floor(window.innerHeight/(r*{_CELL_H})),"
        f"f=Math.max({_MIN_FONT},Math.min(a,b,{_MAX_FONT}));"
        "p.set('fontsize',f);location.replace(location.pathname+'?'+p.toString());}})();</script>"
    )


def _centre() -> str:
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
    """
    return (
        "<style>html,body{height:100%;margin:0}"
        "body{display:flex;align-items:safe center;justify-content:safe center;overflow:auto}</style>"
    )


def _back_overlay() -> str:
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
        # A cabinet pushbutton: round, convex, sitting on a collar it visibly sinks into when
        # pressed. The travel is the point — a flat rectangle gives a touch player no feedback that
        # a tap registered, and this one is deliberately the only control on the page that looks
        # like hardware, because it is the only one that is not part of the game's own screen.
        "<style>#tc-back-fab{position:fixed;right:16px;bottom:16px;z-index:99998;"
        "width:66px;height:66px;padding:0;border-radius:50%;border:2px solid #6d1a0e;"
        "background:radial-gradient(circle at 50% 30%,#ff9166 0%,#ec4a2b 52%,#b31d0d 100%);"
        "color:#2b0803;cursor:pointer;-webkit-tap-highlight-color:transparent;"
        "flex-direction:column;align-items:center;justify-content:center;gap:1px;"
        # Three shadows: the collar it stands on, the drop under the whole thing, and the sheen
        # inside the cap that makes it read as convex rather than as a flat disc.
        "box-shadow:0 6px 0 #6d1a0e,0 9px 14px rgba(0,0,0,.55),"
        "inset 0 2px 7px rgba(255,255,255,.45),inset 0 -3px 8px rgba(0,0,0,.35);"
        "transition:transform .06s linear,box-shadow .06s linear}"
        # Touch devices only. This button exists because a phone has no keys — a desktop browser has
        # Escape, and the footer already says so, which makes a piece of moulded plastic sitting over
        # the terminal pure decoration there. `pointer: coarse` is the same test the auto-fit uses,
        # and it answers for the device rather than for the window: a laptop with a narrow window is
        # still a laptop. Hidden by DEFAULT, so a browser that cannot answer the query gets the
        # keyboard's UI rather than a control it does not need.
        "#tc-back-fab{display:none}"
        "@media (pointer: coarse){#tc-back-fab:not([hidden]){display:flex}}"
        "#tc-back-fab:active{transform:translateY(5px);"
        "box-shadow:0 1px 0 #6d1a0e,0 2px 5px rgba(0,0,0,.5),"
        "inset 0 2px 7px rgba(255,255,255,.35),inset 0 -3px 8px rgba(0,0,0,.35)}"
        "#tc-back-fab .tc-glyph{font-size:21px;line-height:1}"
        "#tc-back-fab .tc-label{font-size:9px;letter-spacing:.14em;font-weight:700}</style>"
        "<button id='tc-back-fab' type='button' aria-label='Back' hidden>"
        "<span class='tc-glyph'>&#9664;</span><span class='tc-label'>BACK</span></button>"
        "<script>(function(){var b=document.getElementById('tc-back-fab');"
        "window.__tcMeta=window.__tcMeta||{};"
        "window.__tcMeta['termcade_back']=function(m){b.hidden=!m.allowed;};"
        # Only the typeface is borrowed from the terminal now — the colours are the button's own, so
        # it stays a piece of the cabinet whatever theme the game is drawing in.
        "var paint=function(){var t=document.querySelector('.xterm');if(!t)return;"
        "b.style.fontFamily=getComputedStyle(t).fontFamily;};"
        "setTimeout(paint,600);setTimeout(paint,2500);"
        "b.addEventListener('click',function(e){e.preventDefault();"
        "var t=document.querySelector('.xterm-helper-textarea');if(!t)return;t.focus();"
        "b.hidden=true;"  # until the app says the next screen has a way back too
        "['keydown','keyup'].forEach(function(k){t.dispatchEvent(new KeyboardEvent(k,"
        f"{{key:'{_BACK_KEY}',code:'{_BACK_CODE}',{_BACK_MODIFIER}keyCode:{_BACK_KEYCODE},"
        f"which:{_BACK_KEYCODE},bubbles:true}}));}});}});}})();</script>"
    )


def _meta_signal() -> str:
    """Listen, in the HEAD, for everything the app says to the page.

    Must be installed before ``textual.js`` opens its websocket — wrapping the constructor after the
    socket exists is too late. What each message *means* is not decided here: a packet is handed to
    whatever registered for its type in ``window.__tcMeta``, so the Back button and the speaker each
    own their own behaviour and neither has to know the other exists.
    """
    return (
        "<script>(function(){window.__tcMeta=window.__tcMeta||{};var W=window.WebSocket;"
        "window.WebSocket=function(u,p){var s=p?new W(u,p):new W(u);"
        "s.addEventListener('message',function(e){if(typeof e.data!=='string')return;"
        "var m;try{m=JSON.parse(e.data);}catch(_){return;}"
        "var h=m&&window.__tcMeta[m[0]];if(h){h(m[1]);}});return s;};"
        "window.WebSocket.prototype=W.prototype;})();</script>"
    )


def _audio_bridge() -> str:
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
    return (
        "<script>(function(){var AC=window.AudioContext||window.webkitAudioContext;if(!AC)return;"
        "var ctx=null,music=null,pending=null,buf={},part={};"
        # A gesture is what a browser will accept an AudioContext from. Any of these count, and the
        # listeners stay: a context can fall back to 'suspended' when a phone is locked or the tab
        # is backgrounded, and the next tap has to be able to bring it round again.
        "var wake=function(){if(!ctx){ctx=new AC();}if(ctx.state==='suspended'){ctx.resume();}"
        "if(pending){var p=pending;pending=null;loop(p);}};"
        "['pointerdown','keydown','touchend'].forEach(function(e){"
        "document.addEventListener(e,wake,{passive:true});});"
        "var decode=function(b64){var s=atob(b64),n=s.length,b=new Uint8Array(n);"
        "for(var i=0;i<n;i++){b[i]=s.charCodeAt(i);}return b;};"
        # int16 little-endian to the float -1..1 WebAudio wants.
        "var buffer=function(bytes,rate){var pcm=new Int16Array(bytes.buffer,0,bytes.length>>1);"
        "var a=ctx.createBuffer(1,pcm.length,rate),c=a.getChannelData(0);"
        "for(var i=0;i<pcm.length;i++){c[i]=pcm[i]/32768;}return a;};"
        "var start=function(a,gain,looping){var s=ctx.createBufferSource(),g=ctx.createGain();"
        "s.buffer=a;s.loop=looping;g.gain.value=gain;s.connect(g);g.connect(ctx.destination);"
        "s.start();return {src:s,gain:g};};"
        # A crossfade runs both loops for its length and drops the outgoing one at the end — the
        # same shape as the engine's Mixer.fade, because it is replacing the same thing.
        "var loop=function(m){if(!ctx){pending=m;return;}var a=buf[m.id];if(!a){pending=m;return;}"
        "var t=ctx.currentTime,f=m.crossfade||0;"
        "if(music&&f>0){var old=music;old.gain.gain.setValueAtTime(old.gain.gain.value,t);"
        "old.gain.gain.linearRampToValueAtTime(0,t+f);old.src.stop(t+f);"
        "music=start(a,0,true);music.gain.gain.setValueAtTime(0,t);"
        "music.gain.gain.linearRampToValueAtTime(m.gain,t+f);return;}"
        "if(music){try{music.src.stop();}catch(_){}}"
        "music=start(a,m.gain,true);};"
        "var handle=function(m){"
        "if(m.action==='chunk'){var p=part[m.id]||(part[m.id]={n:0,total:m.total,s:''});"
        "p.s+=m.data;p.n++;if(p.n<p.total)return;delete part[m.id];"
        # The context may not exist yet (no gesture). Keep the bytes; build the buffer on the way in
        # to `loop`, which only ever runs once there is a context to build it with.
        "var bytes=decode(p.s);var make=function(){buf[m.id]=buffer(bytes,m.rate);};"
        "if(ctx){make();}else{var once=function(){if(ctx){make();"
        "if(pending&&pending.id===m.id){var q=pending;pending=null;loop(q);}"
        "document.removeEventListener('pointerdown',once);"
        "document.removeEventListener('keydown',once);"
        "document.removeEventListener('touchend',once);}};"
        "['pointerdown','keydown','touchend'].forEach(function(e){"
        "document.addEventListener(e,once,{passive:true});});}return;}"
        "if(m.action==='loop'){loop(m);return;}"
        "if(m.action==='once'){if(!ctx||!buf[m.id])return;start(buf[m.id],m.gain,false);return;}"
        "if(m.action==='stop'){if(music){try{music.src.stop();}catch(_){}music=null;}pending=null;}"
        "};window.__tcMeta=window.__tcMeta||{};window.__tcMeta['termcade_audio']=handle;"
        "})();</script>"
    )


def _no_virtual_keyboard() -> str:
    """Stop a phone throwing its on-screen keyboard up on every tap.

    xterm.js keeps a hidden textarea focused to receive keystrokes, and focusing a textarea is what
    tells a mobile browser to open the keyboard — so every tap on the board covered half the screen
    with keys nobody typed on. ``inputmode="none"`` keeps the focus (and with it paste and IME) while
    telling the browser not to offer the keyboard. Desktop browsers ignore it: they have real keys.

    The textarea is created by xterm.js after this runs, and again whenever the terminal is rebuilt,
    so an observer sets the attribute rather than a one-off query.
    """
    return (
        "<script>(function(){var f=function(){"
        "document.querySelectorAll('.xterm-helper-textarea').forEach(function(t){"
        "if(t.getAttribute('inputmode')!=='none'){t.setAttribute('inputmode','none');}});};"
        "new MutationObserver(f).observe(document.documentElement,{childList:true,subtree:true});"
        "document.addEventListener('DOMContentLoaded',f);f();})();</script>"
    )


def _touch_gestures() -> str:
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
    return (
        "<script>(function(){var y=null,x=null,moved=0,swiped=false;"
        "var key=function(name,code){"
        "var t=document.querySelector('.xterm-helper-textarea');if(!t)return;t.focus();"
        "['keydown','keyup'].forEach(function(k){t.dispatchEvent(new KeyboardEvent(k,"
        "{key:name,code:name,keyCode:code,which:code,bubbles:true}));});};"
        "document.addEventListener('touchstart',function(e){"
        "y=e.touches[0].clientY;x=e.touches[0].clientX;moved=0;swiped=false;},{passive:true});"
        "document.addEventListener('touchmove',function(e){"
        "if(y===null)return;var ny=e.touches[0].clientY,nx=e.touches[0].clientX;"
        "var d=y-ny,ax=nx-x;"
        "if(!swiped&&Math.abs(ax)>48&&Math.abs(ax)>Math.abs(ny-y)*2){"
        "swiped=true;if(ax<0){key('ArrowRight',39);}else{key('ArrowLeft',37);}return;}"
        "if(swiped)return;"
        "moved+=Math.abs(d);"
        "if(moved<24||Math.abs(d)<3)return;"
        "var t=document.querySelector('.xterm-screen')||document.body;"
        "t.dispatchEvent(new WheelEvent('wheel',{deltaY:d*2,bubbles:true,cancelable:true}));"
        "y=ny;},{passive:true});"
        "document.addEventListener('touchend',function(){"
        "y=null;x=null;moved=0;swiped=false;},{passive:true});"
        "})();</script>"
    )


def _min_px(min_size: tuple[int, int]) -> tuple[int, int]:
    """The window below which even the smallest font can't fit the game's floor grid."""
    cols, rows = min_size
    return round(cols * _CELL_W * _MIN_FONT), round(rows * _CELL_H * _MIN_FONT)


def _faces() -> tuple[tuple[str, Path], ...]:
    """The embedded faces, in the order the terminal should consult them."""
    return ((_FAMILY, _FONT), (_SYMBOL_FAMILY, _SYMBOL_FONT))


def _favicon() -> str:
    """Point the tab, and a phone's home screen, at the cabinet's icon."""
    if not _ICON.exists():
        return ""
    return (
        f"<link rel='icon' href='/static/{_ICON.name}'>"
        f"<link rel='apple-touch-icon' href='/static/{_ICON.name}'>"
    )


def _font_face(family: str, path: Path) -> str:
    """Point at the font as a *file*, not a 2.4MB base64 blob inlined in the page.

    Inlined, the whole HTML document carried the font: mobile browsers never finished it, fell back
    to a system face, and the glyphs the game draws with went missing. Served from /static it
    streams, caches, and does not block the page."""
    return (
        f"@font-face{{font-family:'{family}';src:url('/static/{path.name}') format('truetype');"
        "font-display:block;}"
    )


def _too_small_gate(min_size: tuple[int, int]) -> tuple[str, str]:
    """A CSS overlay for a game that cannot reflow below ``min_size``. Empty for one that scrolls."""
    min_w, min_h = _min_px(min_size)
    style = (
        f"<style>#tc-toosmall{{position:fixed;inset:0;z-index:99999;display:none;"
        f"background:#000;color:#f2c14e;font-family:monospace;font-size:18px;padding:2rem;"
        f"align-items:center;justify-content:center;text-align:center}}"
        f"@media (max-width:{min_w - 1}px),(max-height:{min_h - 1}px)"
        f"{{#tc-toosmall{{display:flex}}}}</style>"
    )
    return style, '<div id="tc-toosmall">Window too small &mdash; make it bigger to play.</div>'


def _templates_dir(
    fit_size: tuple[int, int],
    min_size: tuple[int, int] | None,
    touch_fit_size: tuple[int, int] | None = None,
) -> Path | None:
    """A one-off templates dir holding textual-serve's page with our font embedded, or ``None`` if
    the upstream template can't be patched — then the game serves with the stock font."""
    template = Path(textual_serve.__file__).resolve().parent / "templates" / "app_index.html"
    if not (template.exists() and all(p.exists() for _, p in _faces())):
        return None
    html = template.read_text(encoding="utf-8")
    if _STOCK_STACK not in html:  # upstream changed shape — don't ship a half-patched page
        return None
    face = "<style>" + "".join(_font_face(f, p) for f, p in _faces()) + "</style>"
    gate, div = _too_small_gate(min_size) if min_size is not None else ("", "")
    # The page is a Jinja2 template (aiohttp_jinja2); wrap our snippets in {% raw %} so their CSS/JS
    # braces (e.g. `{#tc-toosmall`, a Jinja comment open) and the base64 aren't parsed as template tags.
    # The auto-fit goes first in <head> so it runs and reloads before textual.js reads the font size.
    html = html.replace(
        "</head>",
        "{% raw %}"
        + _VIEWPORT
        + _autofit(fit_size, touch_fit_size)
        + _meta_signal()
        + _audio_bridge()
        + _no_virtual_keyboard()
        + _touch_gestures()
        + _centre()
        + _favicon()
        + face
        + gate
        + "{% endraw %}</head>",
        1,
    )
    html = html.replace(
        "</body>", "{% raw %}" + div + _back_overlay() + "{% endraw %}</body>", 1
    )
    # Our font leads the stack: xterm.js renders text and the icons it covers from it, and only the
    # few glyphs it lacks fall through to the stock fonts and the browser's system fallback.
    html = html.replace(_STOCK_STACK, f'"{_FAMILY}", {_STOCK_STACK}')
    out = Path(tempfile.mkdtemp(prefix="termcade-serve-"))
    (out / "app_index.html").write_text(html, encoding="utf-8")
    return out


def _patch_terminal_js(js: Path, families: tuple[str, ...]) -> bool:
    """Put our fonts at the head of the *terminal's* stack, and hold the terminal until they load.

    Both halves are needed. Leading the stack is what makes xterm ask for the fonts at all; awaiting
    ``document.fonts`` is what makes it ask while the answer still matters, since the atlas is built
    once. Left unpatched (upstream changed shape) the game serves with the stock font, as before.
    """
    if not js.exists():
        return False
    src = js.read_text(encoding="utf-8")
    if _TERM_STACK not in src or _ONLOAD not in src:
        return False
    ours = "".join(f"'{f}', " for f in families)
    loads = ",".join(f"document.fonts.load('16px \"{f}\"')" for f in families)
    src = src.replace(_TERM_STACK, ours + _TERM_STACK, 1)
    src = src.replace(
        _ONLOAD,
        "window.onload=async e=>{"
        f"try{{await Promise.all([{loads}]);await document.fonts.ready;}}"
        "catch(_){}"
        'const t=document.querySelectorAll(".textual-terminal")',
        1,
    )
    js.write_text(src, encoding="utf-8")
    return True


def _statics_dir(assets: tuple[Path, ...]) -> Path | None:
    """textual-serve's own static tree, copied, with our fonts and icon added — so they can be
    *served* — and its terminal script patched to draw with them."""
    upstream = Path(textual_serve.__file__).resolve().parent / "static"
    if not (upstream.exists() and all(a.exists() for a in assets)):
        return None
    out = Path(tempfile.mkdtemp(prefix="termcade-static-"))
    shutil.copytree(upstream, out, dirs_exist_ok=True)
    for asset in assets:
        shutil.copy2(asset, out / asset.name)
    _patch_terminal_js(out / "js" / "textual.js", tuple(f for f, _ in _faces()))
    return out


def make_server(
    *,
    port: int,
    public_url: str,
    game: str,
    host: str = "0.0.0.0",
    fit_size: tuple[int, int] = DEFAULT_FIT_SIZE,
    min_size: tuple[int, int] | None = DEFAULT_MIN_SIZE,
    touch_fit_size: tuple[int, int] | None = None,
) -> Server:
    """Build the textual-serve ``Server`` with our patched (font-embedded) page when available,
    else the stock page. Shared by ``serve`` (headless, for Docker) and the desktop launcher.

    ``fit_size`` / ``min_size`` come from the game's ``Game`` descriptor. ``min_size=None`` (a game
    whose screens scroll) means no too-small overlay: zooming past the fit is the player's choice.

    With ``TERMCADE_CODES`` set this is a :class:`~termcade.beta.BetaServer` instead: a passcode at
    the door and a save directory per code. Without it, the open server as before — a player serving
    the game to their own machine should not have to hold a passcode.
    """
    templates = _templates_dir(fit_size, min_size, touch_fit_size)
    statics = _statics_dir(tuple(p for _, p in _faces()) + (_ICON,))
    kwargs: dict[str, object] = {
        "host": host, "port": port, "title": "TermCade", "public_url": public_url
    }
    if templates is not None:
        kwargs["templates_path"] = templates
    if statics is not None:
        kwargs["statics_path"] = statics

    codes = beta.codes_path()
    if codes is None:
        return TermCadeServer(game, **kwargs)  # type: ignore[arg-type]
    return beta.BetaServer(game, codes_path=codes, data_dir=_data_dir(), **kwargs)


def _data_dir() -> Path:
    """The base the beta's per-player directories are made under — the same ``TERMCADE_DATA_DIR``
    the game itself reads (``/data`` in the image), so codes.txt and players/ sit side by side."""
    configured = os.environ.get(beta.DATA_DIR_ENV)
    return Path(configured) if configured else Path.cwd()


def _descriptor_sizes() -> tuple[tuple[int, int], tuple[int, int] | None, tuple[int, int] | None]:
    """Read ``fit_size``/``min_size`` off the game named by ``GAME_FACTORY``.

    Without it (or if the import fails) the page falls back to the engine defaults, which is only
    ever a guess — a page sized to one grid while the game lays out for another opens scrolled.
    """
    factory = os.environ.get("GAME_FACTORY")
    if not factory:
        return DEFAULT_FIT_SIZE, DEFAULT_MIN_SIZE, None
    module_name, _, attr = factory.partition(":")
    game = getattr(importlib.import_module(module_name), attr)()
    return game.fit_size or DEFAULT_FIT_SIZE, game.min_size, game.touch_fit_size


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    public_url = os.environ.get("PUBLIC_URL", f"http://localhost:{port}")
    game = os.environ.get("GAME", "xiaolin")
    fit_size, min_size, touch_fit = _descriptor_sizes()
    make_server(
        port=port, public_url=public_url, game=game,
        fit_size=fit_size, min_size=min_size, touch_fit_size=touch_fit,
    ).serve()


if __name__ == "__main__":
    main()
