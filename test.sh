#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "=== Python tests ==="
uv run pytest -v

echo ""
echo "=== JavaScript tests ==="
cd "$ROOT/frontend"
npm test

echo ""
echo "All tests passed."
