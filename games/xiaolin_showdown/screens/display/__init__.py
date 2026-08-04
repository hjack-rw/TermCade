"""Display/rendering helpers — pure functions and data, no ``Screen`` subclasses here.

- :mod:`.format` — the base display formatting: card/points labels, names, tooltips.
- :mod:`.headline` — Wu prose built on that base: headlines and the Game Log's titles.
- :mod:`.duel_board` — renders the showdown board and its Game-Log story from duel state.
- :mod:`.temple_render` — renders TempleScreen's three panels.
- :mod:`._logo` — the start screen's ASCII art.

This package deliberately re-exports nothing — import the submodule you mean.
"""
