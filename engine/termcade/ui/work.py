"""``work`` — Textual's worker decorator, with the engine's answer to a crash.

Every decision a screen asks a player for runs in a worker: the deposit confirm, the Morpher's element,
the Early Bird's price. Textual's own ``@work`` defaults to ``exit_on_error=True``, so an exception in
any of them **takes the whole game down** — mid-run, with a traceback where the board was, and whatever
was not saved is gone.

That is the wrong trade for a game. A bug in one screen's dialog should cost you that dialog, not your
run. This decorator is the same one with ``exit_on_error=False``, and :meth:`EngineApp.on_worker_state_changed`
picks the failure up and puts the exception on screen instead — named, so it can be reported, and
dismissible, so the player is handed back to the game they were playing.

Use this everywhere a game or an engine screen would have used ``textual.work``. It is not a wrapper for
its own sake: the default is a crash, and the default is not what we want.
"""

from __future__ import annotations

from functools import partial
from typing import Any

from textual import work as _textual_work

work: Any = partial(_textual_work, exit_on_error=False)
