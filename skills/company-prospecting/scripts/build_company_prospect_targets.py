#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))

from sync_company_prospect_tracker import (  # type: ignore
    company_key,
    outreach_tracker_path,
    parse_sections,
    repo_root_from_args,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List company prospect targets that still need names or Apollo emails."
    )
    parser.add_argument("--root", default=None, help="Optional repo root override")
    parser.add_argument("--limit", type=int, default=0, help="Optional max rows to print")
    args = parser.parse_args()

    repo_root = repo_root_from_args(args.root)
    tracker = outreach_tracker_path(repo_root)
    if not tracker.exists():
        raise SystemExit(f"Prospect tracker does not exist yet: {tracker}")

    queue_rows, prospect_rows = parse_sections(tracker.read_text().splitlines())

    prospect_map: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in prospect_rows:
        prospect_map.setdefault(company_key(row["Company"], row["Posting Key"]), []).append(row)

    targets = []
    for row in queue_rows:
        key = company_key(row["Company"], row["Posting Key"])
        prospects = prospect_map.get(key, [])
        ready_count = sum(1 for prospect in prospects if prospect.get("Email Status", "").strip().lower() == "ready")
        if len(prospects) < 3 or ready_count < len(prospects):
            targets.append((row, len(prospects), ready_count))

    if args.limit > 0:
        targets = targets[: args.limit]

    print(f"Company prospect targets: {len(targets)}")
    print("")
    for index, (row, prospect_count, ready_count) in enumerate(targets, start=1):
        print(
            f"{index}. {row['Company']} | {row['Role']} | Fit {row['Fit Score'] or '?'} | "
            f"Prospects {prospect_count}/3 | Ready emails {ready_count}"
        )
        print(f"   Posting Key: {row['Posting Key']}")
        print(f"   Job Link: {row['Job Link']}")
        if row["Notes"].strip():
            print(f"   Notes: {row['Notes']}")
        print("")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
