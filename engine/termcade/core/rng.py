"""Deterministic, JSON-serializable RNG.

Wraps ``random.Random`` (never the global ``random``) so a game's randomness is
reproducible from a seed and can be snapshotted into a save file. :meth:`Rng.spawn` gives an
independent sub-stream for randomness that must not perturb play — decoration, flavour, anything a
rules change would be embarrassed by.
"""

from __future__ import annotations

import hashlib
import random
import secrets
from typing import Any, MutableSequence, Sequence, TypeVar

T = TypeVar("T")

# random.getstate() -> (version, tuple[int, ...], float | None); JSON-safe form is a list.
RngState = list[Any]


def resolve_seed(seed: int | str | None) -> int:
    """None -> fresh entropy; str -> stable hash; int -> itself."""
    if seed is None:
        return secrets.randbits(63)
    if isinstance(seed, int):
        return seed
    digest = hashlib.sha256(seed.encode("utf-8")).digest()[:8]
    return int.from_bytes(digest, "big")


class Rng:
    def __init__(self, seed: int | str | None = None) -> None:
        self._seed = resolve_seed(seed)
        self._random = random.Random(self._seed)

    @property
    def seed(self) -> int:
        return self._seed

    def randint(self, a: int, b: int) -> int:
        return self._random.randint(a, b)

    def choice(self, seq: Sequence[T]) -> T:
        return self._random.choice(seq)

    def shuffle(self, seq: MutableSequence[Any]) -> None:
        self._random.shuffle(seq)

    def spawn(self, label: str) -> "Rng":
        """An independent stream, deterministic from this one but drawing from it *without*
        consuming it.

        Anything cosmetic must use one of these. Drawing decoration off the main stream would shift
        every roll after it, so adding a purely visual flourish would silently change how the game
        plays — the seed would stop meaning what it meant.

        Derived from the seed, the label, and the parent's *current* state, so successive spawns as
        play advances give different streams, and the same seed always replays the same ones.
        """
        version, internal, gauss_next = self._random.getstate()
        material = f"{self._seed}:{label}:{version}:{internal}:{gauss_next}"
        return Rng(int.from_bytes(hashlib.sha256(material.encode()).digest()[:8], "big"))

    def get_state(self) -> RngState:
        """JSON-safe snapshot of the internal generator state."""
        version, internal, gauss_next = self._random.getstate()
        return [version, list(internal), gauss_next]

    def set_state(self, state: RngState) -> None:
        """Restore from a :meth:`get_state` snapshot (survives a JSON round-trip)."""
        version, internal, gauss_next = state
        self._random.setstate((version, tuple(internal), gauss_next))
