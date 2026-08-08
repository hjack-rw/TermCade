"""The shape of a battle, as ``mechanics/`` needs to see it.

``flow.battle.Round``/``Side`` are the real, concrete state — but they are owned by ``flow/``, one
layer above ``mechanics/``. A lower-level module typed directly against them would depend upward,
so this declares only the structural subset ``mechanics/`` actually reads and mutates; the concrete
dataclasses satisfy it with no import in either direction. See :mod:`.resolve` and :mod:`.prize`.
"""

from __future__ import annotations

from typing import Protocol

from ..schema.models import Card


class SideLike(Protocol):
    queue: list[Card]
    suffered: list[Card]
    amplifiers: list[Card]
    jack_bot: list[Card]
    spent: list[Card]
    result: list[int]
    base_negated: bool
    offence_negated: bool
    defence_negated: bool
    boost_negated: bool
    element_as: str | None
    element_cancelled: bool
    ward: set[str]
    shielded: set[str]

    def mine(self) -> list[Card]: ...


class RoundLike(Protocol):
    stat: str

    def sides(self, is_player: bool) -> tuple[SideLike, SideLike]: ...
