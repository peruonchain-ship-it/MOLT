#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --frozen
uv run --frozen python -c 'from molt.config import Config; from molt.db import Database; Database(Config.from_env()); print("Dependencias y almacenamiento privado preparados.")'
