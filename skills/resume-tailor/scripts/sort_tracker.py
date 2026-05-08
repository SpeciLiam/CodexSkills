#!/usr/bin/env python3
"""Sort the application tracker markdown table by any column."""

from __future__ import annotations

import argparse
from pathlib import Path

from update_application_tracker import (
    DEFAULT_COLUMNS,
    build_row,
    escape_cell,
    normalize,
    parse_rows,
    refresh_visualizer_data,
    render_tracker,
    repo_root_from_args,
    row_from_cells,
    split_row,
    tracker_path,
    truthy,
    TITLE_LINE,
    DESCRIPTION_LINE,
)

NUMERIC_COLUMNS = {"Fit Score"}
DATE_COLUMNS = {"Date Added"}
BOOL_COLUMNS = {"Applied", "Reach Out", "Referral"}


def sort_key(row: dict[str, str], column: str) -> tuple:
    value = row.get(column, "").strip()

    if column in NUMERIC_COLUMNS:
        try:
            return (0, float(value))
        except ValueError:
            return (1, 0.0)

    if column in DATE_COLUMNS:
        # YYYY-MM-DD sorts lexicographically, missing dates go last
        return (0, value) if value else (1, "")

    if column in BOOL_COLUMNS:
        return (0,) if truthy(value) else (1,)

    return (0, normalize(value)) if value else (1, "")


def render_sorted(rows: list[str], column: str, descending: bool) -> str:
    parsed = []
    for line in rows:
        row = row_from_cells(split_row(line))
        if row is not None:
            parsed.append(row)

    parsed.sort(key=lambda r: sort_key(r, column), reverse=descending)

    # Reuse render_tracker's header/summary logic by passing pre-built row lines
    row_lines = [build_row(r) for r in parsed]
    return render_tracker(row_lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sort the application tracker by a column.")
    parser.add_argument(
        "--by",
        default="Date Added",
        help=f"Column to sort by. One of: {', '.join(DEFAULT_COLUMNS)}",
    )
    parser.add_argument(
        "--desc",
        action="store_true",
        default=False,
        help="Sort descending (default: ascending, except Date Added defaults to descending)",
    )
    parser.add_argument(
        "--asc",
        action="store_true",
        default=False,
        help="Force ascending sort",
    )
    parser.add_argument("--root", default=None, help="Optional repo root override")
    args = parser.parse_args()

    column = args.by
    if column not in DEFAULT_COLUMNS:
        close = [c for c in DEFAULT_COLUMNS if args.by.lower() in c.lower()]
        if len(close) == 1:
            column = close[0]
        else:
            print(f"Unknown column '{args.by}'. Valid columns: {', '.join(DEFAULT_COLUMNS)}")
            return 1

    # Date Added and Fit Score default to descending; everything else defaults to ascending
    if args.asc:
        descending = False
    elif args.desc:
        descending = True
    else:
        descending = column in DATE_COLUMNS | NUMERIC_COLUMNS

    repo_root = repo_root_from_args(args.root)
    path = tracker_path(repo_root)

    if not path.exists():
        print(f"Tracker not found: {path}")
        return 1

    lines = path.read_text().splitlines()
    _, rows = parse_rows(lines)

    if not rows:
        print("No rows found in tracker.")
        return 0

    output = render_sorted(rows, column, descending)
    path.write_text(output)
    refresh_visualizer_data(repo_root)

    direction = "desc" if descending else "asc"
    print(f"Sorted {len(rows)} rows by '{column}' ({direction}) → {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
