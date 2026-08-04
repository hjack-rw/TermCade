"""The structural shape of the game's data — dataclasses and their loading, no behavior.

- :mod:`.models` — the plain dataclasses (Card, Character, Power, Player...).
- :mod:`.state` — ``XiaolinState``, the engine's persisted ``GameState`` for this game.
- :mod:`.catalog` — loads the immutable card catalog from the bundled SQLite DB.
- :mod:`.constants` — pool-structural constants, not player knobs (see ``config`` for those).

This package deliberately re-exports nothing — import the submodule you mean.
"""
