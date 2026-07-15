"""The journal — what happened in this run, in the order it happened.

**A toast is a thing you can miss.** It shows for a few seconds in a corner and then it is gone, and
the game does not stop while it is up: the opponent's whole turn, the price they named, what the
mystery Wu turned out to be worth. A player who looked away has no way back to any of it, and "what
just happened?" is not a question a game should refuse to answer.

So every notification is written down as it is raised (see ``EngineApp.notify``), and a game may add
what it does *without* a popup — a Wu banked, a showdown settled. The journal is the record; the
Game Log screen is one way of reading it.

Not persisted. A journal belongs to a **run**, and it is emptied when a new state is dealt (see
``GameContext.state``) — a loaded save opens on an empty log rather than the tail of somebody else's
game, which would be a lie told in order to have something to show.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    """One thing that happened: which turn it happened in, what it was about, and what it said.

    ``title`` is the toast's title where it had one (``Opponent's move``) and empty where it did not.
    All plain — the journal is `core`, and it stores what was *said*, not how it looked.
    """

    turn: int
    title: str
    message: str


class Journal:
    """An ordered record of a run, oldest first, cut into turns.

    **The turn is the unit a player thinks in.** "What did they do last turn?" is the question the log
    exists to answer, and a flat scroll of forty lines cannot answer it — you have to remember where
    one turn ended, which is precisely what you came here having forgotten. So every line is stamped
    with the turn it happened in, and the game says when a turn is over (:meth:`next_turn`).

    Capped, and quietly: a long run raises a few hundred notifications and nobody scrolls back through
    a thousand. The cap protects the memory of a very long session, not the reader.
    """

    LIMIT = 500

    def __init__(self) -> None:
        self._entries: list[Entry] = []
        self._turn = 1

    @property
    def entries(self) -> tuple[Entry, ...]:
        return tuple(self._entries)

    @property
    def turn(self) -> int:
        return self._turn

    def add(self, message: str, *, title: str = "") -> None:
        """Write a line under the turn in play. A blank one is dropped — it records nothing."""
        message = message.strip()
        if not message:
            return
        self._entries.append(Entry(turn=self._turn, title=title.strip(), message=message))
        del self._entries[: max(0, len(self._entries) - self.LIMIT)]

    def next_turn(self) -> None:
        """The turn is over — everything written from here belongs to the next one.

        The *game* says when, because only the game knows what a turn is: for Xiaolin it closes when a
        showdown does, and an abandoned one closes nothing.
        """
        self._turn += 1

    def clear(self) -> None:
        self._entries.clear()
        self._turn = 1

    def __len__(self) -> int:
        return len(self._entries)
