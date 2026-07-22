"""Everything the served PAGE is made of: its CSS, its scripts, and the fonts it declares.

Pure string building. Nothing here opens a file, starts a server or touches the network — each
function answers "what goes in the page", and :mod:`termcade.serve` decides where to put it. That
split is why this module is testable by reading its output, and it is most of the reason `serve.py`
stopped being two files' worth of one.

The browser features the game needs all live here: the auto-fit that sizes the terminal to the
window, the meta channel the app talks to the page through, the WebAudio bridge, the touch
gestures, the arcade Back button, and the font declarations that reach xterm without patching it.
"""

from __future__ import annotations

from pathlib import Path

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
BACK_MODIFIER = "shiftKey:true,"

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
    return (
        "<script>(function(){var p=new URLSearchParams(location.search);"
        f"var touch=window.matchMedia('(pointer: coarse)').matches;"
        f"var c=touch?{t_cols}:{cols},r=touch?{t_rows}:{rows};"
        f"var a=Math.floor(window.innerWidth/(c*{CELL_W})),"
        f"b=Math.floor(window.innerHeight/(r*{CELL_H})),"
        f"f=Math.max({MIN_FONT},Math.min(a,b,{MAX_FONT}));"
        "var current=parseInt(p.get('fontsize'),10);"
        "var shape=window.innerWidth+'x'+window.innerHeight;"
        "var settled=null;try{settled=sessionStorage.getItem('tcFit');}catch(e){}"
        "if(current!==f&&settled!==shape){"
        "try{sessionStorage.setItem('tcFit',shape);}catch(e){}"
        "p.set('fontsize',f);location.replace(location.pathname+'?'+p.toString());return;}"
        "})();</script>"
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
    return (
        "<script>(function(){"
        # Touch only, like the width cap. A desktop window already re-fits continuously while it is
        # dragged, and `visualViewport` fires on zoom there — so this would add refits to a platform
        # that never needed them and was not asked about.
        "if(!window.matchMedia('(pointer: coarse)').matches)return;"
        "var kick=function(){window.dispatchEvent(new Event('resize'));};"
        "var settle=function(){[60,250,600,1000].forEach(function(d){setTimeout(kick,d);});};"
        "window.addEventListener('orientationchange',settle);"
        "if(window.screen&&window.screen.orientation){"
        "window.screen.orientation.addEventListener('change',settle);}"
        "if(window.visualViewport){window.visualViewport.addEventListener('resize',settle);}"
        "})();</script>"
    )


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
    return (
        "<style>html,body{height:100%;margin:0}"
        "body{display:flex;align-items:safe center;justify-content:safe center;overflow:auto}"
        "#terminal{max-height:100dvh}</style>"
    )


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
        f"{{key:'{BACK_KEY}',code:'{BACK_CODE}',{BACK_MODIFIER}keyCode:{BACK_KEYCODE},"
        f"which:{BACK_KEYCODE},bubbles:true}}));}});}});}})();</script>"
    )


def meta_signal() -> str:
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
        # Chunks are PLACED by their `seq`, not appended in arrival order. The socket delivers in
        # order today, which is exactly why appending looked correct — but the sender states a
        # sequence number, and a guarantee nobody checks is not a guarantee. Placing also makes a
        # duplicate harmless instead of corrupting the tune.
        "if(m.action==='chunk'){var p=part[m.id]||(part[m.id]={n:0,total:m.total,a:[]});"
        "if(p.a[m.seq]===undefined){p.a[m.seq]=m.data;p.n++;}"
        "if(p.n<p.total)return;delete part[m.id];"
        # The context may not exist yet (no gesture). Keep the bytes; build the buffer on the way in
        # to `loop`, which only ever runs once there is a context to build it with.
        "var bytes=decode(p.a.join(''));var make=function(){buf[m.id]=buffer(bytes,m.rate);};"
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


def no_virtual_keyboard() -> str:
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
    return (
        "<script>(function(){var go=function(){var s=document.createElement('script');"
        # textual.js starts the terminal from `window.onload`. Injected late, it misses that event
        # entirely — the script loads, defines its handler, and nothing ever calls it, which shows
        # up as a page that renders no terminal at all and reports no error. So when the document
        # has already finished loading, we call the handler it just installed.
        "s.onload=function(){if(document.readyState==='complete'"
        "&&typeof window.onload==='function'){window.onload();}};"
        f"s.src='{{{{ config.static.url }}}}js/textual.js';document.head.appendChild(s);}};"
        "if(!document.fonts){go();return;}"
        f"Promise.all([{families},document.fonts.load(\"16px 'Roboto Mono'\")])"
        ".catch(function(){}).then(function(){return document.fonts.ready;})"
        ".catch(function(){}).then(go);})();</script>"
    )


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
    style = (
        f"<style>#tc-toosmall{{position:fixed;inset:0;z-index:99999;display:none;"
        f"background:#000;color:#f2c14e;font-family:monospace;font-size:18px;padding:2rem;"
        f"align-items:center;justify-content:center;text-align:center}}"
        f"@media (max-width:{min_w - 1}px),(max-height:{min_h - 1}px)"
        f"{{#tc-toosmall{{display:flex}}}}</style>"
    )
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
