# TermCade

## Disclaimer

**Xiaolin Showdown, the game bundled here, is a non-commercial fan project** — not affiliated with,
endorsed, sponsored, or approved by Warner Bros., Cartoon Network, or any rights holder. _Xiaolin
Showdown_, its characters, and the Shen Gong Wu names are trademarks of their respective owners,
used here descriptively in a non-commercial context.

## What this is

A reusable **Textual** TUI engine for terminal games, plus the games that run on it, in one monorepo. The engine is the long-lived _cabinet_; each game is a finite _cartridge_ that plugs into it.

The engine layers with a one-directional purity boundary — `core` (TUI-agnostic services: saves, settings, rng, state) never imports Textual, so it stays unit-testable without a terminal; only `ui` touches Textual.

## Games on the cabinet

- **[Xiaolin Showdown](games/xiaolin_showdown/README.md)** _(1.3, beta)_ — a terminal card duel. See its own README for how to play, the card list, and the lore.

## Controls

Click any option, or drive it from the keyboard — **Tab** enters focus mode (highlights the first option; press Tab again to leave it), then **↑ / ↓** move the highlight and **Enter** selects. In-game actions also have single-key shortcuts, shown along the footer. Every cartridge inherits this control scheme from the engine.

**On a phone** there is no keyboard and none is needed — focus mode is hidden there rather than advertised as a key nobody can press. Tap an option and drag up or down to scroll. The arcade pushbutton in the corner is Back — it appears only on a screen that has somewhere to go, and only on a touch device.

## Simple play

For anyone who just wants to click and go, no terminal or Docker needed: grab **`TermCade.exe`** — one file, put it anywhere, double-click it. It runs the bundled game in a maximized browser window and auto-sizes to fit your screen; a small console shows the address and stays open while you play (close it to stop). Nothing to install: no Python, no Docker, no terminal. First launch takes a few seconds (it self-unpacks); if SmartScreen prompts once, choose _More info → Run anyway_.

Build it yourself (needs Python this once), then share the single file:

```bash
pip install -e ".[build]"
python scripts/build_launcher.py        # -> dist/TermCade.exe  (one movable file, no folder)
```

## Layout

```
engine/termcade/    # the reusable engine package (import: termcade)
  core/             # TUI-agnostic services — saves, settings, rng, state (never imports textual)
  app/              # wiring seam — Game descriptor + GameContext
  ui/               # Textual layer — EngineApp, screens, widgets, theme
games/              # the games (first: xiaolin_showdown)
tests/              # engine (no TTY) + Pilot UI tests, plus a separate browser (Playwright) suite
```

## Develop

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"     # Windows; use bin/ on POSIX
pytest

python -m termcade                         # boot the engine attract scene
```

To actually play a game from source, see that game's own README — e.g.
[games/xiaolin_showdown/README.md](games/xiaolin_showdown/README.md).

## Closed beta

Serving a game to other people needs two things the open server has no answer for: a way to keep
strangers out, and a way to stop testers overwriting each other's saves. One passcode does both —
checked at the door, then hashed into that player's own save directory.

```bash
printf 'beta-alpha-1\nbeta-bravo-2\n' > codes.txt    # one per line; # comments ignored
docker compose -f docker-compose.yml -f docker-compose.beta.yml --profile beta up
```

The tunnel container prints a `https://*.trycloudflare.com` URL. Put it in `PUBLIC_URL` and bring
the stack up again, then hand each tester `<url>/?code=<their code>`. Revoking a tester is deleting
their line from `codes.txt` — it's re-read on every request. Set `TERMCADE_CODES` to switch the
gate on outside Docker; unset, the server is open as before.

**Sound plays in the browser, not on the server** — a container has no audio device, so a served
session sends its samples to the page and WebAudio mixes them there. Nothing is fetched: the game
generates its own audio, so the tune travels once (about 1.2MB for a 22s loop) and every replay
after that is free. Browsers refuse sound to a page nobody has touched, so playback starts on the
player's first tap or keypress rather than on load.

## Fonts

Games draw their board with plain Unicode symbols picked for _text_ (monochrome) presentation. The icons render as monochrome glyphs anywhere a font covers them; the only catch is that a bare terminal font can lack a glyph and show tofu (☐). A monospace font with good symbol coverage is bundled under `engine/termcade/assets/`, which is also where the browser build reads it from:

- `0xProtoNerdFont-Regular.ttf` — [0xProto](https://github.com/0xType/0xProto), SIL Open Font License
- `TermCadeSymbols.ttf` — a subset of [DejaVu Sans Mono](https://dejavu-fonts.github.io/) (see `DejaVu-LICENSE`, alongside it) covering the punctuation, arrow, technical, box, shape and symbol blocks 0xProto leaves out

Install the first and select it in your terminal to play locally. The **browser build** (`serve`)
embeds both, so nothing needs installing and nothing depends on what the device happens to have —
0xProto is consulted first, and the symbol subset only for what it lacks.
