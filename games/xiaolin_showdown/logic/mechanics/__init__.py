"""The rules themselves — what a Wu power does, and how a showdown scores.

Three modules, in the order a reader wants them:

- :mod:`.powers` — the reference table: every ``(trigger, effect)`` pair a card can carry, the
  :class:`~.powers.Mechanic` it buys, and the rule in one line.
- :mod:`.resolve` — a played card becomes queue entries, dispatched on its mechanic.
- :mod:`.scoring` — initiative before a showdown, end values within one.

Nothing here decides anything: the bot's choices live in :mod:`..bot`, the stage order in
:mod:`..duel`, and the temple's turn economy in :mod:`..actions` and :mod:`..turn`. Import the
submodule you mean — this package deliberately re-exports nothing.
"""
