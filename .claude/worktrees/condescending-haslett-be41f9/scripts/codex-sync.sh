#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_DIR="${1:-$REPO_ROOT/skills}"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
TARGET_DIR="$CODEX_HOME/skills"

mkdir -p "$TARGET_DIR"

if [[ ! -d "$SKILLS_DIR" ]]; then
  echo "Skills directory not found: $SKILLS_DIR" >&2
  exit 1
fi

synced=0

while IFS= read -r -d '' skill_dir; do
  skill_name="$(basename "$skill_dir")"
  target="$TARGET_DIR/$skill_name"

  if [[ -L "$target" || -e "$target" ]]; then
    rm -rf "$target"
  fi

  ln -s "$skill_dir" "$target"
  echo "Synced $skill_name -> $target"
  synced=$((synced + 1))
done < <(find "$SKILLS_DIR" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)

echo "Done. Synced $synced skill(s) into $TARGET_DIR"
