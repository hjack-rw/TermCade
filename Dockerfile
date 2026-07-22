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

# Box-drawing + truecolour need a real terminal profile; saves live on a volume. GAME_FACTORY lets
# `serve` size the browser page from the cartridge's own descriptor rather than a copy of it.
ENV TERMCADE_DATA_DIR=/data \
    TERM=xterm-256color \
    COLORTERM=truecolor \
    PYTHONUNBUFFERED=1 \
    GAME_FACTORY=xiaolin_showdown.game:build_game

# Install the wheel with its `serve` extra (browser mode); terminal mode needs only the wheel.
# The extra is asked for BY NAME rather than naming textual-serve and a version here: this line used
# to pin ==1.1.3 while pyproject said ~=1.1, so the image could ship a version nothing was tested
# against, and the pin silently contradicted the decision recorded next to the dependency.
COPY --from=builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir "$(ls /tmp/*.whl)[serve]" && rm -rf /tmp/*.whl

RUN useradd --create-home --uid 1000 player && mkdir -p /data && chown player /data
VOLUME ["/data"]
EXPOSE 8000

COPY --chmod=0755 docker/entrypoint.sh /usr/local/bin/entrypoint.sh
USER player
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["xiaolin"]
