#!/bin/sh
# TermCade container entrypoint.
#
#   docker run -it termcade                # play Xiaolin Showdown in the terminal (default)
#   docker run -it termcade termcade       # boot the engine attract scene
#   docker run -p 8000:8000 termcade serve # serve the game to a browser on :8000
#
# "serve" launches the browser gateway (textual-serve); GAME/PORT tune what and where.
# Anything else is exec'd directly, so any installed console script works.
set -e

if [ "${1:-}" = "serve" ]; then
    # Browser mode. termcade.serve embeds the bundled font (glyphs render with no host install) and
    # reads GAME / PORT / PUBLIC_URL from the environment. PUBLIC_URL must be a *connectable* host,
    # not 0.0.0.0, or the browser's websocket can't connect back — override it behind a real hostname.
    exec python -m termcade.serve
fi

exec "${@:-xiaolin}"
