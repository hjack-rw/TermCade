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

# TERMCADE_SERVE is the same choice as the "serve" argument above, made through the environment
# instead of the command: some hosts (Back4app Containers, confirmed) run the image's own default
# CMD verbatim with no way to override it, only env vars. Without this, such a host always got the
# terminal-mode default and never bound a port — the healthcheck failed with nothing listening.

if [ "$(id -u)" = "0" ]; then
    # Root only on a host that mounts something at $TERMCADE_DATA_DIR after the image's own chown
    # already ran (Railway Volumes, among others) — the mount hides that layer's ownership under
    # whatever the volume actually has, usually root. Fix it, then become `player` for everything
    # else: a bare image with no external mount never hits this, since `player` already owns /data.
    chown player "$TERMCADE_DATA_DIR" 2>/dev/null || true
    exec su player -s /bin/sh -c 'exec "$0" "$@"' -- "$0" "$@"
fi

if [ "${1:-}" = "serve" ] || [ -n "${TERMCADE_SERVE:-}" ]; then
    # Browser mode. termcade.serve embeds the bundled font (glyphs render with no host install) and
    # reads GAME / PORT / PUBLIC_URL from the environment. PUBLIC_URL must be a *connectable* host,
    # not 0.0.0.0, or the browser's websocket can't connect back — override it behind a real hostname.
    exec python -m termcade.serve
fi

exec "${@:-xiaolin}"
