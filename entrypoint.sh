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

# Run migrations if a database already exists (skip on first start — init_db() handles fresh installs)
DB_PATH="${AM_DB_PATH:-/data/am_discovery.db}"
if [ -f "$DB_PATH" ]; then
    echo "[entrypoint] Running database migrations…"
    uv run python migrate.py
fi

exec uv run gunicorn -c gunicorn.conf.py "wsgi:app"
