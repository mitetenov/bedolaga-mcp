# Bedolaga MCP — reproducible production image.
#
# Base: python:3.14-slim (full bugfix support until Oct 2030). The previous
# 3.11-slim is in security-only phase (ends Oct 2027); 3.14 exactly matches the
# runtime the pinned dependency versions were verified on, so the protocol
# behaviour in the image is identical to every local smoke run.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install pinned runtime deps first so this layer only rebuilds when
# requirements.txt changes (everything is pinned, no open bounds).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the whole package and both compatibility entrypoints. The implementation
# lives in bedolaga_mcp/, not in two root files; the launchers stay for
# compatibility with existing docker/desktop commands.
COPY bedolaga_mcp/ ./bedolaga_mcp/
COPY http_server.py bedolaga_server.py ./

# Run as a non-privileged user. /app stays root-owned (read-only for the app):
# the server keeps no state on disk, so the runtime only needs read access and
# a HOME for any cache that a library might create.
RUN useradd --create-home --uid 1000 --user-group appuser
USER appuser

EXPOSE 3100

# Run the HTTP server by default. Override with --entrypoint for stdio mode.
CMD ["python3", "http_server.py"]
