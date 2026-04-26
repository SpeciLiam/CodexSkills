#!/usr/bin/env python3

from __future__ import annotations

import argparse

from application_fit import load_profile, score_application, should_reach_out
from notion_sync import sync_tracker_to_notion, token_from_env
from update_application_tracker import (
    build_row,
    ensure_tracker,
    parse_rows,
    render_tracker,
    repo_root_from_args,
    row_from_cells,
    split_row,
    tracker_path,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill fit scores and recruiter reach-out flags in the tracker.")
    parser.add_argument("--root", default=None, help="Optional repo root override")
    parser.add_argument(
        "--respect-manual-reach-out",
        action="store_true",
        help="Preserve existing Reach Out values instead of recomputing them from the score threshold.",
    )
    parser.add_argument("--sync-notion", action="store_true", help="Also sync Fit Score and Reach Out values to Notion")
    parser.add_argument("--notion-token-env", default="NOTION_TOKEN", help="Environment variable holding the Notion integration token")
    parser.add_argument("--update-notion-title", action="store_true", help="Also update the Notion database title count when syncing")
    parser.add_argument("--dry-run-notion", action="store_true", help="Preview Notion sync without changing Notion")
    args = parser.parse_args()

    repo_root = repo_root_from_args(args.root)
    profile = load_profile(repo_root)
    tracker = tracker_path(repo_root)
    ensure_tracker(tracker)

    lines = tracker.read_text().splitlines()
    _, rows = parse_rows(lines)

    updated_rows: list[str] = []
    for row_line in rows:
        row = row_from_cells(split_row(row_line))
        if row is None:
            updated_rows.append(row_line)
            continue

        score = score_application(row, profile)
        row["Fit Score"] = str(score)
        if not args.respect_manual_reach_out or not row.get("Reach Out", "").strip():
            row["Reach Out"] = "Yes" if should_reach_out(score, profile) else ""
        updated_rows.append(build_row(row))

    tracker.write_text(render_tracker(updated_rows))

    if args.sync_notion:
        token = token_from_env(args.notion_token_env)
        sync_tracker_to_notion(
            repo_root=repo_root,
            token=token,
            update_title=args.update_notion_title,
            dry_run=args.dry_run_notion,
        )

    print(tracker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
