#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTCOMES = ROOT / "application-trackers" / "outcomes.jsonl"
ALLOWED_OUTCOMES = {"submitted", "manual", "archived", "skipped", "rejected_after_apply", "oa", "interview", "offer"}


def band(score: int) -> str:
    if score >= 80:
        return "high"
    if score >= 55:
        return "medium"
    return "low"


def load_existing(path: Path) -> set[tuple[str, str]]:
    existing: set[tuple[str, str]] = set()
    if not path.exists():
        return existing
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        existing.add((str(row.get("postingKey") or ""), str(row.get("outcome") or "")))
    return existing


def main() -> int:
    parser = argparse.ArgumentParser(description="Append an idempotent application outcome event.")
    parser.add_argument("--job-link", default="")
    parser.add_argument("--posting-key", required=True)
    parser.add_argument("--company", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--source", default="")
    parser.add_argument("--predicted-confidence-score", type=int, default=0)
    parser.add_argument("--outcome", required=True, choices=sorted(ALLOWED_OUTCOMES))
    parser.add_argument("--blocker", default=None)
    parser.add_argument("--submit-ms", type=int, default=None)
    args = parser.parse_args()

    key = args.posting_key.strip()
    if not key:
        raise SystemExit("--posting-key is required")

    OUTCOMES.parent.mkdir(parents=True, exist_ok=True)
    existing = load_existing(OUTCOMES)
    if (key, args.outcome) in existing:
        print(f"Outcome already logged: {key} {args.outcome}")
        return 0

    score = max(0, min(100, args.predicted_confidence_score))
    event: dict[str, Any] = {
        "loggedAt": datetime.now(timezone.utc).isoformat(),
        "postingKey": key,
        "company": args.company,
        "role": args.role,
        "source": args.source,
        "predictedConfidenceScore": score,
        "predictedConfidenceBand": band(score),
        "outcome": args.outcome,
        "blocker": args.blocker,
        "submitMs": args.submit_ms,
    }
    with OUTCOMES.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
    print(f"Logged outcome: {key} {args.outcome}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
