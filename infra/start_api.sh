#!/bin/sh
set -eu

mkdir -p "$(dirname "$STEELCHAIN_DB")"
if [ ! -f "$STEELCHAIN_DB" ]; then
  python -m steelchain generate --db "$STEELCHAIN_DB" --seed 20261122 --scenario normal --days 1096
fi
python -m steelchain validate --db "$STEELCHAIN_DB"
exec uvicorn steelchain.agents.api:app --host 0.0.0.0 --port 8000
