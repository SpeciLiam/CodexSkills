#!/usr/bin/env python3
"""Per-row codex exec orchestrator for finish-app-script.

For each queued row in /tmp/fa_script_run_state.json:
  1. Build a tight per-row prompt
  2. Spawn `codex exec --cd $REPO --sandbox workspace-write -m <model> -o <out>`
  3. Wait up to --timeout seconds
  4. Re-read the state file → check the row's outcome (submitted|manual|archived)
  5. Update counters; run circuit breaker; commit/push every 5 confirmed
  6. Loop to next queued row

The orchestrator owns: queue iteration, timeouts, circuit breaker, commit/push.
The spawned agent owns: browser flow, form filling, submission, state writeback.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = ROOT / "skills" / "finish-app-script"
OPERATING_CARD = SKILL_DIR / "OPERATING_CARD.md"
STATE_PATH = Path("/tmp/fa_script_run_state.json")
OUTPUT_DIR = Path("/tmp/fa_script_outputs")
TRACKER_PATH = "application-trackers/applications.md"
CACHE_PATH = "application-visualizer/src/data/tracker-data.json"

DEFAULT_MODEL = "gpt-5.5"
DEFAULT_TIMEOUT_S = 360
CIRCUIT_BREAKER_THRESHOLD = 3
COMMIT_EVERY = 5

DONE_STATES = {"submitted", "manual", "archived", "skipped"}


PROMPT_TEMPLATE = """\
Read skills/finish-app-script/OPERATING_CARD.md before starting. Follow it strictly.

You are completing ONE job application. Single-row mode: process this row, write the outcome, exit.

Company: {company}
Role: {role}
URL: {jobLink}
Resume PDF: {resumePdf}
Posting key: {postingKey}
Source: {source}
State item key: {key}
Notes carried from tracker: {notes}

Use Codex Computer Use (computer-use@openai-bundled) for the live browser flow.

Dropdowns / typeahead / combo boxes / multi-select: open the menu, click the actual option, verify the rendered chip/value. Never just type into a typeahead and move on — the field will be silently rejected.

Confidence decision after final review:
- HIGH (every required field covered, no blocker): click submit, capture confirmation evidence, run skills/gmail-application-refresh/scripts/update_application_status.py with --status Applied --applied Yes, set state="submitted".
- MEDIUM (FRQ or one uncertain field): fill all safe fields, generate best-effort answer from Liam's profile, leave the tab open at the cleanest review point, set state="manual" with blocker like "FRQ review: <question>".
- HARD blocker (login/2FA/CAPTCHA/Workday/account creation/legal signature/AI-deterrent verification): set state="manual" with the exact blocker.
- Posting closed/404/redirected to a different role: set state="archived".

Then UPDATE /tmp/fa_script_run_state.json — find the items[] entry where key == "{key}" and set:
  state: submitted | manual | archived
  result: short factual note
  blocker: exact blocker text (when manual)
  confirmationEvidence: confirmation page text / email / portal status (when submitted)
  updatedAt: ISO 8601 timestamp (UTC)

Refresh the visualizer cache when submitted:
  python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py

Do NOT commit or push. The orchestrator owns commits.

Exit when done.
"""


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        raise SystemExit(
            f"Missing run state at {STATE_PATH}.\n"
            "Run: python3 skills/finish-app-script/scripts/build_queue.py"
        )
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def write_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(STATE_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(STATE_PATH)


def next_queued(state: dict[str, Any]) -> dict[str, Any] | None:
    for item in state.get("items", []):
        if item.get("state") == "queued":
            return item
    return None


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)[:80] or "row"


def build_prompt(item: dict[str, Any]) -> str:
    return PROMPT_TEMPLATE.format(
        company=item.get("company") or "",
        role=item.get("role") or "",
        jobLink=item.get("jobLink") or "",
        resumePdf=item.get("resumePdf") or "",
        postingKey=item.get("postingKey") or "",
        source=item.get("source") or "",
        notes=item.get("notes") or item.get("manualReason") or "",
        key=item.get("key") or "",
    )


def mark_outcome_in_state(key: str, *, state_value: str, **fields: Any) -> None:
    state = load_state()
    for item in state.get("items", []):
        if item.get("key") == key:
            item["state"] = state_value
            item["updatedAt"] = now_iso()
            for k, v in fields.items():
                if v is not None:
                    item[k] = v
            break
    write_state(state)


def get_outcome(key: str) -> dict[str, Any] | None:
    state = load_state()
    for item in state.get("items", []):
        if item.get("key") == key:
            return item
    return None


def spawn_codex_exec(prompt: str, output_file: Path, model: str, timeout_s: int) -> tuple[int, str]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        "codex", "exec",
        "--cd", str(ROOT),
        "--sandbox", "workspace-write",
        "-m", model,
        "-o", str(output_file),
        prompt,
    ]
    try:
        result = subprocess.run(
            cmd,
            timeout=timeout_s,
            capture_output=True,
            text=True,
        )
        return result.returncode, (result.stdout or "") + (result.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, f"timeout after {timeout_s}s"


def commit_and_push(*, push: bool, message: str) -> bool:
    add = subprocess.run(
        ["git", "-C", str(ROOT), "add", TRACKER_PATH, CACHE_PATH],
        capture_output=True, text=True,
    )
    if add.returncode != 0:
        print(f"  git add failed: {add.stderr.strip()}")
        return False
    diff = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--cached", "--quiet"],
        capture_output=True,
    )
    if diff.returncode == 0:
        print("  Nothing staged for tracker/cache; skipping commit.")
        return False
    commit = subprocess.run(
        ["git", "-C", str(ROOT), "commit", "-m", message],
        capture_output=True, text=True,
    )
    if commit.returncode != 0:
        print(f"  git commit failed: {commit.stderr.strip()}")
        return False
    print(f"  ✓ committed: {message}")
    if push:
        push_result = subprocess.run(
            ["git", "-C", str(ROOT), "push", "origin", "main"],
            capture_output=True, text=True,
        )
        if push_result.returncode != 0:
            print(f"  git push failed: {push_result.stderr.strip()}")
            return False
        print("  ✓ pushed origin/main")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Per-row codex exec orchestrator for finish-app-script")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model for codex exec (default: {DEFAULT_MODEL})")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S, help="Per-row timeout in seconds")
    parser.add_argument("--max-rows", type=int, default=0, help="Cap rows processed (0 = drain queue)")
    parser.add_argument("--no-commit", action="store_true", help="Skip auto-commit every 5 confirmed submissions")
    parser.add_argument("--no-push", action="store_true", help="Commit but do not push to origin/main")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts without invoking codex exec")
    args = parser.parse_args()

    state = load_state()
    queue_total = sum(1 for it in state.get("items", []) if it.get("state") == "queued")
    print(f"finish-app-script orchestrator | queue: {queue_total} | model: {args.model} | timeout: {args.timeout}s")
    if args.dry_run:
        print("(dry run — no codex exec invocations)")

    processed = 0
    consecutive_manual = 0
    submitted_since_push = 0
    summary = {"submitted": [], "manual": [], "archived": [], "skipped": []}

    while True:
        if args.max_rows and processed >= args.max_rows:
            print(f"\nReached --max-rows {args.max_rows}, stopping.")
            break

        item = next_queued(load_state())
        if not item:
            print("\nQueue drained.")
            break

        key = item.get("key") or ""
        company = item.get("company") or "?"
        role = item.get("role") or "?"
        confidence = item.get("confidenceBand") or "?"
        action = item.get("action") or "?"
        url = item.get("jobLink") or ""
        print(f"\n[{processed + 1}] {company} | {role}")
        print(f"  key={key}  confidence={confidence}  action={action}")
        print(f"  url={url}")

        if args.dry_run:
            print("  (would spawn codex exec; skipping)")
            mark_outcome_in_state(key, state_value="skipped", result="dry-run")
            summary["skipped"].append(f"{company} | {role}")
            processed += 1
            continue

        prompt = build_prompt(item)
        out_file = OUTPUT_DIR / f"{safe_filename(key)}.txt"
        started_at = time.time()
        rc, _err = spawn_codex_exec(prompt, out_file, args.model, args.timeout)
        elapsed = time.time() - started_at
        processed += 1

        if rc == -1:
            print(f"  ✗ timeout after {args.timeout}s — marking manual")
            mark_outcome_in_state(
                key,
                state_value="manual",
                blocker=f"Exec timeout {args.timeout}s",
                result="orchestrator timeout",
            )
            summary["manual"].append(f"{company} | exec timeout")
            consecutive_manual += 1
        elif rc != 0:
            print(f"  ✗ codex exec exited rc={rc} after {elapsed:.0f}s — marking manual")
            mark_outcome_in_state(
                key,
                state_value="manual",
                blocker=f"codex exec rc={rc}",
                result="orchestrator non-zero exit",
            )
            summary["manual"].append(f"{company} | exec rc={rc}")
            consecutive_manual += 1
        else:
            outcome = get_outcome(key) or {}
            outcome_state = outcome.get("state")
            if outcome_state not in DONE_STATES:
                print(f"  ✗ agent exited without writing outcome (still 'queued') — marking manual")
                mark_outcome_in_state(
                    key,
                    state_value="manual",
                    blocker="Agent exited without writing outcome",
                    result="no state writeback",
                )
                summary["manual"].append(f"{company} | no state writeback")
                consecutive_manual += 1
            elif outcome_state == "submitted":
                print(f"  ✓ submitted in {elapsed:.0f}s")
                summary["submitted"].append(f"{company} | {role}")
                submitted_since_push += 1
                consecutive_manual = 0
            elif outcome_state == "manual":
                blocker = outcome.get("blocker") or outcome.get("result") or "no blocker recorded"
                print(f"  → manual ({elapsed:.0f}s): {blocker}")
                summary["manual"].append(f"{company} | {blocker}")
                consecutive_manual += 1
            elif outcome_state == "archived":
                reason = outcome.get("result") or "archived"
                print(f"  ≡ archived ({elapsed:.0f}s): {reason}")
                summary["archived"].append(f"{company} | {reason}")
                consecutive_manual = 0
            else:
                print(f"  ? state={outcome_state} ({elapsed:.0f}s)")
                summary["skipped"].append(f"{company} | state={outcome_state}")

        if consecutive_manual >= CIRCUIT_BREAKER_THRESHOLD:
            print(f"\n⚠ Circuit breaker tripped: {consecutive_manual} consecutive manual outcomes. Stopping.")
            break

        if not args.no_commit and submitted_since_push >= COMMIT_EVERY:
            today = dt.date.today().isoformat()
            print(f"\n→ {submitted_since_push} confirmed submissions since last push, committing...")
            commit_and_push(
                push=not args.no_push,
                message=f"Apply: {submitted_since_push} confirmed submissions {today}",
            )
            submitted_since_push = 0

    if not args.no_commit and submitted_since_push > 0:
        today = dt.date.today().isoformat()
        print(f"\n→ Final commit: {submitted_since_push} pending submissions")
        commit_and_push(
            push=not args.no_push,
            message=f"Apply: {submitted_since_push} confirmed submissions {today}",
        )

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Submitted: {len(summary['submitted'])}")
    for s in summary["submitted"]:
        print(f"  • {s}")
    print(f"Manual: {len(summary['manual'])}")
    for m in summary["manual"]:
        print(f"  • {m}")
    print(f"Archived: {len(summary['archived'])}")
    for a in summary["archived"]:
        print(f"  • {a}")
    if summary["skipped"]:
        print(f"Skipped: {len(summary['skipped'])}")
        for sk in summary["skipped"]:
            print(f"  • {sk}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
