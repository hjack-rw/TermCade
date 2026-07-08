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

# Box-drawing + truecolour need a real terminal profile; saves live on a volume.
ENV TERMCADE_DATA_DIR=/data \
    TERM=xterm-256color \
    COLORTERM=truecolor \
    PYTHONUNBUFFERED=1

# Install the wheel plus textual-serve (browser mode); the terminal mode needs only the wheel.
COPY --from=builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl textual-serve==1.1.3 && rm -rf /tmp/*.whl

RUN useradd --create-home --uid 1000 player && mkdir -p /data && chown player /data
VOLUME ["/data"]
EXPOSE 8000

COPY --chmod=0755 docker/entrypoint.sh /usr/local/bin/entrypoint.sh
USER player
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["xiaolin"]
