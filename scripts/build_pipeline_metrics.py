#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTCOMES = ROOT / "application-trackers" / "outcomes.jsonl"
DB_PATH = ROOT / "application-trackers" / "trackers.sqlite"
OUTPUT = ROOT / "application-visualizer" / "src" / "data" / "pipeline-metrics.json"
CAPTURE_DIR = Path("/tmp/codexskills-job-intake")
SEEN_JOBS = CAPTURE_DIR / "seen_jobs.json"


def parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def load_outcomes(since: datetime) -> list[dict[str, Any]]:
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
        if logged and logged >= since:
            events.append(event)
    return events


def queue_depth() -> dict[str, int]:
    if not DB_PATH.exists():
        return {"readyToApply": 0, "resumeTailored": 0, "manualApplyNeeded": 0, "intakeUnprocessed": 0}
    with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
        app_counts = dict(
            conn.execute(
                """
                SELECT status, COUNT(*) FROM applications
                WHERE removed_at IS NULL AND COALESCE(applied, '') != 'Yes'
                GROUP BY status
                """
            ).fetchall()
        )
        intake_unprocessed = conn.execute(
            """
            SELECT COUNT(*) FROM intake
            WHERE removed_at IS NULL AND status IN ('New', 'Queued')
            """
        ).fetchone()[0]
    return {
        "readyToApply": int(app_counts.get("Ready to Apply", 0)),
        "resumeTailored": int(app_counts.get("Resume Tailored", 0)),
        "manualApplyNeeded": int(app_counts.get("Manual Apply Needed", 0)),
        "intakeUnprocessed": int(intake_unprocessed),
    }


def capture_mtime(source: str) -> str:
    path = CAPTURE_DIR / f"{source}_capture.json"
    if not path.exists():
        return ""
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def intake_health() -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    captured = Counter()
    repeated = 0
    total_recent = 0
    if SEEN_JOBS.exists():
        try:
            data = json.loads(SEEN_JOBS.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            data = {}
        entries = data.get("entries", {}) if isinstance(data, dict) else {}
        if isinstance(entries, dict):
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            for key, entry in entries.items():
                if not isinstance(entry, dict):
                    continue
                source = str(key).split(":", 1)[0]
                first_seen = parse_time(str(entry.get("firstSeenAt") or ""))
                last_seen = parse_time(str(entry.get("lastSeenAt") or ""))
                if first_seen and first_seen.date() == today:
                    captured[source] += 1
                if last_seen and last_seen >= cutoff:
                    total_recent += 1
                    if first_seen and last_seen != first_seen:
                        repeated += 1
    return {
        "linkedinLastRun": capture_mtime("linkedin"),
        "greenhouseLastRun": capture_mtime("greenhouse"),
        "linkedinCapturedToday": captured["linkedin"],
        "greenhouseCapturedToday": captured["greenhouse"],
        "linkedinCacheHitRate": round(repeated / total_recent, 3) if total_recent else 0,
    }


def build(window_days: int) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    events = load_outcomes(since)
    daily: dict[str, Counter[str]] = defaultdict(Counter)
    outcome_counts = Counter()
    source_scores: dict[str, list[int]] = defaultdict(list)
    blockers = Counter()
    for event in events:
        logged = parse_time(str(event.get("loggedAt") or ""))
        if not logged:
            continue
        outcome = str(event.get("outcome") or "")
        bucket = "submitted" if outcome in {"submitted", "oa", "interview", "offer"} else outcome
        if bucket not in {"submitted", "manual", "archived"}:
            bucket = "submitted" if outcome else "manual"
        daily[logged.date().isoformat()][bucket] += 1
        outcome_counts[bucket] += 1
        source_scores[str(event.get("source") or "unknown")].append(int(event.get("predictedConfidenceScore") or 0))
        if outcome == "manual":
            blockers[str(event.get("blocker") or "unspecified")] += 1

    days = [(since + timedelta(days=offset)).date().isoformat() for offset in range(window_days + 1)]
    applications_per_day = [
        {
            "date": day,
            "submitted": daily[day]["submitted"],
            "manual": daily[day]["manual"],
            "archived": daily[day]["archived"],
        }
        for day in days
    ]
    total = sum(outcome_counts.values()) or 1
    avg_by_source = []
    for source, scores in sorted(source_scores.items()):
        avg = round(sum(scores) / len(scores), 1) if scores else 0
        avg_by_source.append({"source": source, "avgScore": avg, "band": "high" if avg >= 80 else "medium" if avg >= 55 else "low"})
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "windowDays": window_days,
        "applicationsPerDay": applications_per_day,
        "submitSuccessRate": {
            "submitted": round(outcome_counts["submitted"] / total, 3),
            "manual": round(outcome_counts["manual"] / total, 3),
            "archived": round(outcome_counts["archived"] / total, 3),
        },
        "avgConfidenceBySource": avg_by_source,
        "topBlockers": [{"reason": reason, "count": count} for reason, count in blockers.most_common(8)],
        "queueDepth": queue_depth(),
        "intakeHealth": intake_health(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build pipeline metrics JSON for the application visualizer.")
    parser.add_argument("--window-days", type=int, default=7)
    args = parser.parse_args()
    payload = build(args.window_days)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
