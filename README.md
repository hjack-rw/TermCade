# TermCade

A reusable **Textual** TUI engine for terminal games, plus the games that run on it, in one monorepo. The engine is the long-lived *cabinet*; each game is a finite *cartridge* that plugs into it.

The engine layers with a one-directional purity boundary — `core` (TUI-agnostic services: saves, settings, rng, state) never imports Textual, so it stays unit-testable without a terminal; only `ui` touches Textual.

## Games

- **Xiaolin Showdown** — Terminal Deck builder. Pick a Character and duel a Bot across a seven-phase showdown: commit stakes, name the Challenge stat and elemental Background, play your Cards, and race to the Point limit. Only the winner gets the Shen Gong Wu!

## Play — no terminal, no Docker

For anyone who just wants to click and go: grab **`TermCade.exe`** — one file, put it anywhere, double-click it. It runs the game in a maximized browser window and auto-sizes to fit your screen; a small console shows the address and stays open while you play (close it to stop). Nothing to install: no Python, no Docker, no terminal. First launch takes a few seconds (it self-unpacks); if SmartScreen prompts once, choose *More info → Run anyway*.

Build it yourself (needs Python this once), then share the single file:

```bash
pip install -e ".[build]"
python build_launcher.py        # -> dist/TermCade.exe  (one movable file, no folder)
```

If the package is already installed, `xiaolin-play` does the same thing — serve locally and open the browser — without freezing an executable.

## Layout

```
engine/termcade/    # the reusable engine package (import: termcade)
  core/             # TUI-agnostic services — saves, settings, rng, state (never imports textual)
  app/              # wiring seam — Game descriptor + GameContext
  ui/               # Textual layer — EngineApp, screens, widgets, theme
games/              # the games (first: xiaolin_showdown)
tests/              # core (no TTY) + Pilot UI tests
```

## Develop & play

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"     # Windows; use bin/ on POSIX
pytest

python -m termcade                         # boot the engine attract scene
xiaolin                                    # play Xiaolin Showdown (needs a real terminal)
xiaolin-play                               # play in the browser — serve + auto-open (needs the [serve] extra)
```

## Fonts

Games draw their board with plain Unicode symbols picked for *text* (monochrome) presentation. The icons render as monochrome glyphs anywhere a font covers them; the only catch is that a bare terminal font can lack a glyph and show tofu (☐). A monospace font with good symbol coverage is bundled under `fonts/`:

- `0xProtoNerdFont-Regular.ttf` — [0xProto](https://github.com/0xType/0xProto), SIL Open Font License

Install it and select it in your terminal to play locally. On Windows the few glyphs it misses (the gear, for one) resolve automatically through the system's Segoe UI Symbol. The **browser build** (`serve`) embeds the font, so no install is needed there — and any glyph it lacks falls back to the browser's own system fonts, still monochrome.

## Disclaimer

Xiaolin Showdown here is a non-commercial **fan project** — not affiliated with, endorsed, sponsored, or approved by Warner Bros., Cartoon Network, or any rights holder. *Xiaolin Showdown*, its characters, and the Shen Gong Wu names are trademarks of their respective owners, used here descriptively in a non-commercial context.
