#!/usr/bin/env python3

from __future__ import annotations

import argparse

from notion_sync import repo_root_from_args, sync_tracker_to_notion, token_from_env


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync markdown tracker values to Notion.")
    parser.add_argument("--root", default=None, help="Optional repo root override")
    parser.add_argument("--posting-key", default=None, help="Optional single posting key to sync")
    parser.add_argument("--token-env", default="NOTION_TOKEN", help="Environment variable holding the Notion integration token")
    parser.add_argument("--update-title", action="store_true", help="Also update the Notion database title count")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be synced without changing Notion")
    parser.add_argument("--full", action="store_true", help="Sync every supported tracker property, not only scores")
    args = parser.parse_args()

    repo_root = repo_root_from_args(args.root)
    token = token_from_env(args.token_env)
    result = sync_tracker_to_notion(
        repo_root=repo_root,
        token=token,
        posting_key=args.posting_key,
        update_title=args.update_title,
        dry_run=args.dry_run,
        full=args.full,
    )
    print(
        f"rows={result['rows_considered']} updated={result['updated']} "
        f"skipped={result['skipped']} missing={result['missing']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
