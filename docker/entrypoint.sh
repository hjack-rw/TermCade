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
    # Bind all interfaces, but the browser's websocket URL must be a *connectable* host, not
    # 0.0.0.0 — public_url drives that. Override PUBLIC_URL when serving behind a real hostname.
    port="${PORT:-8000}"
    exec python -c "from textual_serve.server import Server; Server('${GAME:-xiaolin}', host='0.0.0.0', port=${port}, title='TermCade', public_url='${PUBLIC_URL:-http://localhost:${port}}').serve()"
fi

exec "${@:-xiaolin}"
