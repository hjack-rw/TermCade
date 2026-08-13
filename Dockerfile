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

COPY --chmod=0755 docker/entrypoint.sh /usr/local/bin/entrypoint.sh
USER player
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["xiaolin"]
