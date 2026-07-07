# TermCade

A reusable **Textual** TUI engine for terminal games, plus the games that run on it, in one monorepo. The engine is the long-lived *cabinet*; each game is a finite *cartridge* that plugs into it.

The engine layers with a one-directional purity boundary — `core` (TUI-agnostic
services: saves, settings, rng, state) never imports Textual, so it stays unit-testable without a terminal; only `ui` touches Textual.

## Layout

```
engine/termcade/    # the reusable engine package (import: termcade)
  core/             # TUI-agnostic services — saves, settings, rng, state (never imports textual)
  app/              # wiring seam — Game descriptor + GameContext
  ui/               # Textual layer — EngineApp, screens, widgets, theme
games/              # the games (first: xiaolin_showdown)
tests/              # core (no TTY) + Pilot UI tests
```

## Develop

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"     # Windows; use bin/ on POSIX
pytest
python -m termcade                         # boot the engine
```
