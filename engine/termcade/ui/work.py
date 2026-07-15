"""``work`` — Textual's ``@work`` with ``exit_on_error=False``.

Textual's default takes the WHOLE APP down on an exception in any worker, and every dialog a screen
raises runs in one. `EngineScreen.on_worker_state_changed` catches the dead worker and shows the error
instead. Use this everywhere a screen would have used ``textual.work``.
"""

from __future__ import annotations

from functools import partial
from typing import Any

from textual import work as _textual_work

work: Any = partial(_textual_work, exit_on_error=False)
