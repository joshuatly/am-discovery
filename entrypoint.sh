#!/bin/sh
set -e

# On first run, seed config from the bundled example
if [ ! -f /data/config.json ]; then
    echo "[entrypoint] /data/config.json not found — copying from example"
    cp /app/config.json.example /data/config.json
fi

# Symlink persistent files into the app directory
ln -sf /data/config.json /app/config.json
ln -sf /data/bearer_token.txt /app/bearer_token.txt 2>/dev/null || true

exec uv run python server.py
