# syntax=docker/dockerfile:1

# --- build stage: turn the monorepo into a single wheel --------------------
FROM python:3.12-slim AS builder
WORKDIR /src
RUN pip install --no-cache-dir build
COPY pyproject.toml README.md ./
COPY engine ./engine
COPY games ./games
RUN python -m build --wheel --outdir /dist

# --- runtime stage ---------------------------------------------------------
FROM python:3.12-slim
LABEL org.opencontainers.image.title="TermCade" \
      org.opencontainers.image.description="Textual TUI game engine + Xiaolin Showdown"

# Box-drawing + truecolour need a real terminal profile; saves live on a volume. GAME is the console
# command `serve` runs in browser mode; GAME_FACTORY lets it size the page from the cartridge's own
# descriptor rather than a copy of it. The image ships one game, so both name it explicitly.
ENV TERMCADE_DATA_DIR=/data \
    TERM=xterm-256color \
    COLORTERM=truecolor \
    PYTHONUNBUFFERED=1 \
    GAME=xiaolin \
    GAME_FACTORY=xiaolin_showdown.game:build_game

# Install the wheel with its `serve` extra (browser mode); terminal mode needs only the wheel.
# The extra is asked for BY NAME rather than naming textual-serve and a version here: this line used
# to pin ==1.1.3 while pyproject said ~=1.1, so the image could ship a version nothing was tested
# against, and the pin silently contradicted the decision recorded next to the dependency.
COPY --from=builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir "$(ls /tmp/*.whl)[serve]" && rm -rf /tmp/*.whl

RUN useradd --create-home --uid 1000 player && mkdir -p /data && chown player /data
# No `VOLUME` instruction: Railway's builder rejects it outright ("use Railway Volumes" instead of
# the Docker-native directive), and `docker-compose.yml`'s own `tc_saves:/data` mount works without
# it — Compose's `volumes:` doesn't need the image to declare one. Railway's own Volume, attached to
# this service at /data on the platform side, is what persists saves/`codes.txt` there in production.
EXPOSE 8000

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
# chmod as its own RUN, not COPY --chmod=0755: Back4app's Kaniko builder was observed silently
# dropping the exec bit from COPY --chmod, so the entrypoint launched fine everywhere already
# tested (Railway, Bot-Hosting) but failed on Back4app with "exec ...: permission denied:
# unknown" at container start. RUN chmod is the one form every builder (classic Docker,
# BuildKit, Kaniko) applies consistently.
RUN chmod 0755 /usr/local/bin/entrypoint.sh
# No USER here: a host that mounts an external volume at $TERMCADE_DATA_DIR (Railway Volumes, among
# others) replaces this layer's chown'd /data with the volume's own root-owned filesystem at
# container start — `player` can no longer write to it. The container starts as root so the
# entrypoint can chown whatever actually landed at that path, then drops to `player` itself before
# running the real command.
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["xiaolin"]
