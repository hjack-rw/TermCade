"""The mandatory path through a game — the screens a run must pass through start to finish.

- :mod:`.start` — the root menu.
- :mod:`.character_select` — pick a dragon, and a boss if the ladder's open.
- :mod:`.temple` — the between-duel hub.
- :mod:`.duel` — one showdown, stepped through a phase at a time.
- :mod:`.outcome` — the final scoreboard.

This package deliberately re-exports nothing — import the submodule you mean.
"""
