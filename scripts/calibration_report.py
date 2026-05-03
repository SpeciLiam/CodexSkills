#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTCOMES = ROOT / "application-trackers" / "outcomes.jsonl"
SUCCESS = {"submitted", "oa", "interview", "offer"}
BANDS = [("high", lambda score: score >= 80), ("medium", lambda score: 55 <= score < 80), ("low", lambda score: score < 55)]


def parse_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_events(since: datetime, source: str | None) -> list[dict[str, Any]]:
    if not OUTCOMES.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in OUTCOMES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        logged = parse_time(str(event.get("loggedAt") or ""))
        if not logged or logged < since:
            continue
        if source and str(event.get("source") or "").lower() != source.lower():
            continue
        events.append(event)
    return events


def pct(count: int, total: int) -> str:
    return "0%" if total == 0 else f"{(count / total) * 100:.0f}%"


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    by_band: dict[str, Counter[str]] = {name: Counter() for name, _ in BANDS}
    by_source: dict[str, Counter[str]] = defaultdict(Counter)
    blockers = Counter(str(event.get("blocker") or "").strip() for event in events if event.get("outcome") == "manual")
    score_by_source: dict[str, list[int]] = defaultdict(list)
    for event in events:
        score = int(event.get("predictedConfidenceScore") or 0)
        outcome = str(event.get("outcome") or "")
        source = str(event.get("source") or "unknown") or "unknown"
        for band, predicate in BANDS:
            if predicate(score):
                by_band[band][outcome] += 1
                break
        by_source[source][outcome] += 1
        score_by_source[source].append(score)

    source_submit_rate = {
        source: {
            "n": sum(counter.values()),
            "submitRate": sum(counter[outcome] for outcome in SUCCESS) / max(1, sum(counter.values())),
        }
        for source, counter in by_source.items()
    }
    avg_source_score = {
        source: round(sum(scores) / len(scores), 1)
        for source, scores in score_by_source.items()
        if scores
    }
    return {
        "n": len(events),
        "byBand": {band: dict(counter) for band, counter in by_band.items()},
        "bySource": {source: dict(counter) for source, counter in by_source.items()},
        "sourceSubmitRate": source_submit_rate,
        "avgSourceScore": avg_source_score,
        "topBlockers": [{"reason": reason or "unspecified", "count": count} for reason, count in blockers.most_common(10)],
    }


def print_text(summary: dict[str, Any], since_label: str) -> None:
    print(f"Confidence calibration (since {since_label}, N={summary['n']})")
    print("=" * 52)
    for band in ("high", "medium", "low"):
        outcomes = Counter(summary["byBand"].get(band, {}))
        total = sum(outcomes.values())
        score_label = {"high": "80+", "medium": "55-79", "low": "<55"}[band]
        parts = ", ".join(f"{outcome} {pct(count, total)}" for outcome, count in outcomes.most_common()) or "no data"
        print(f"Band {band:<6} (score {score_label}): actual: {parts}")
    print("Per-source submit rate:")
    for source, item in sorted(summary["sourceSubmitRate"].items()):
        print(f"  {source}: {item['submitRate'] * 100:.0f}% (n={item['n']})")
    print("Top blockers (manual outcomes):")
    for blocker in summary["topBlockers"]:
        print(f"  {blocker['reason']}: {blocker['count']}")
    print("Confidence drift candidates:")
    for source, item in sorted(summary["sourceSubmitRate"].items()):
        rate = item["submitRate"]
        if item["n"] >= 3 and rate < 0.7:
            print(f"  - source={source} submit rate {rate * 100:.0f}%; consider lowering source weight")
        elif item["n"] >= 3 and rate > 0.85:
            print(f"  - source={source} submit rate {rate * 100:.0f}%; consider raising source weight")


def main() -> int:
    parser = argparse.ArgumentParser(description="Report confidence calibration from recorded application outcomes.")
    parser.add_argument("--since", help="Start date YYYY-MM-DD; default is the last 30 days.")
    parser.add_argument("--source", help="Limit to one source.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    if args.since:
        since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
        since_label = args.since
    else:
        since = datetime.now(timezone.utc) - timedelta(days=30)
        since_label = "last 30 days"
    summary = summarize(load_events(since, args.source))
    if args.format == "json":
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print_text(summary, since_label)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
