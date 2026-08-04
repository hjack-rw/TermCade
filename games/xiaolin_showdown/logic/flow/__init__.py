"""The game-loop machinery — applied the same way regardless of who's playing.

Dealing (:mod:`.setup`), the temple turn (:mod:`.turn`, :mod:`.actions`), a showdown
(:mod:`.duel`, :mod:`.battle`), power effects (:mod:`.power_effects`), the opponent's decisions
(:mod:`.bot`, :mod:`.temple_ai`), summon-pool selection (:mod:`.summons`), stat growth
(:mod:`.training`), card wear (:mod:`.wear`), and how a run ends (:mod:`.outcome`).

This package deliberately re-exports nothing — import the submodule you mean.
"""
