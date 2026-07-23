"""Entry point for the parkervcp Python egg, which boots the server with ``python main.py``.

The egg offers no free-form environment variables, so the host facts the server reads — ``PUBLIC_URL``,
the beta gate's paths — live in an untracked ``.env`` beside this file on the container disk (written by
the panel's env editor). Same reason ``codes.txt`` is not committed: this repo is public. Anything
already in the real environment wins (``setdefault``), so the file is a floor, not an override.

``GAME`` and ``GAME_FACTORY`` are set here, not read from the panel: ``GAME`` is run through a shell by
textual-serve, so a hand-typed value is a foot-gun — a stray quote or the wrong ``PATH`` turns the whole
string into one "command not found". Built from ``sys.executable`` it is an absolute path with no PATH
lookup and no quoting to get wrong, so serving the game never depends on a field someone can mistype.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ENV_FILE = Path(__file__).with_name(".env")
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _, _value = _line.partition("=")
            os.environ.setdefault(_key.strip(), _value.strip())

# Force, not setdefault: this must win over whatever is in the panel .env, because getting it wrong
# there is exactly the failure this removes. The running interpreter launches the game as a module.
os.environ["GAME"] = f"{sys.executable} -m xiaolin_showdown"
os.environ.setdefault("GAME_FACTORY", "xiaolin_showdown.game:build_game")

from termcade.serve import main  # noqa: E402 — after the env file loads, so it reads the host facts

main()
