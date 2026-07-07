"""Pure Xiaolin Showdown rules, ported from the reference ``src/`` (no textual, no I/O).

Everything here is game-specific and testable without a TTY. Randomness is always
injected as an engine ``Rng`` so a seed reproduces the exact game; presentation
(the reference's ANSI ``_info`` helpers) is dropped — screens render these models.
"""
