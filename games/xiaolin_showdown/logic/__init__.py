"""Pure Xiaolin Showdown rules — no textual, no I/O.

Everything here is game-specific and testable without a TTY. Randomness is always
injected as an engine ``Rng`` so a seed reproduces the exact game; presentation is
left to the screens, which render these models.
"""
