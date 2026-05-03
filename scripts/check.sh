#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
python3 scripts/validate_tracker.py
python3 scripts/mirror_to_sqlite.py
