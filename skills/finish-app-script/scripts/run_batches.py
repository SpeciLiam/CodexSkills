#!/usr/bin/env python3
"""Rotating parent orchestrator for finish-app-script.

This is intentionally different from run_queue.py:

- run_queue.py spawns one tiny child agent per application row.
- run_batches.py spawns one fresh Codex CLI process for a small batch, usually
  two rows, and that process owns the live Chrome/Computer Use workflow.

The goal is to get the context-reset benefit without making every single row a
separate browser-worker process.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
STATE_PATH = Path("/tmp/fa_script_run_state.json")
OUTPUT_DIR = Path("/tmp/fa_script_batch_outputs")
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_BATCH_SIZE = 2
DEFAULT_TIMEOUT_S = 1800
DEFAULT_CHILD_SANDBOX = "danger-full-access"
DONE_STATES = {"submitted", "manual", "archived", "skipped"}
SYSTEMIC_BLOCKER_TERMS = (
    "apple event error -1743",
    "browser access blocker",
    "chrome computer use unavailable",
    "computer use access denied",
    "computer use approval denied",
    "computer use itself is unavailable",
    "appnotfound(\"chrome\")",
)


BATCH_PROMPT = """\
Read skills/finish-app-script/OPERATING_CARD.md before starting. Follow the
standing answers and submission rules strictly, with this batch override:

You are a fresh parent application agent, not a per-row subagent. Use Codex
Computer Use directly for Chrome in this process. Do not spawn subagents or
parallel browser workers.

Process up to {batch_size} queued application rows from
/tmp/fa_script_run_state.json, then exit cleanly. Before each row, reread the
state file and pick the first items[] entry with state == "queued". Keep one
browser flow active at a time.

For each row:
- Always open a brand-new Chrome tab before navigating to the jobLink, including
  the first row in this batch. Never navigate over an existing application,
  email, search, or handoff tab.
- Complete the live application with the row's resumePdf. During file upload,
  the macOS file picker may default to the previous application's file; before
  confirming any upload, verify the selected path exactly matches the current
  row's resumePdf from /tmp/fa_script_run_state.json.
- Submit high-confidence routine applications.
- If submitted successfully and confirmation evidence is captured, close that
  application tab before starting the next row.
- For medium confidence, fill every safe field, leave the tab at the cleanest
  review point, and mark manual with an exact blocker. Keep that handoff tab
  open even if this Codex process is about to exit.
- For hard blockers (account creation, login, SMS/authenticator 2FA,
  interactive CAPTCHA, Workday, legal signature/attestation, AI-deterrent
  verification), mark manual with the exact blocker and leave any useful
  partially completed tab open for Liam.
- Do not check legal acknowledgements, arbitration agreements, applicant
  certifications, true-and-complete attestations, or signature-equivalent boxes.
  If one is required, stop before checking it, mark manual, and leave the tab
  open for Liam review.
- For closed/404/mismatched postings, mark archived.
- After any outcome, continue the next row from a brand-new tab when batch
  capacity remains. Do not reuse a submitted, partially completed, or handoff
  tab for another application.
- After every outcome, update /tmp/fa_script_run_state.json for that row:
  state, result, blocker when manual, confirmationEvidence when submitted,
  updatedAt.
- When submitted, run:
  python3 skills/gmail-application-refresh/scripts/update_application_status.py
  with --company, --role, --posting-key, --status Applied, --applied Yes, and a
  short application-submitted note; then refresh the visualizer cache with:
  python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py

Stop early if Chrome/Computer Use itself is unavailable, because that is a
systemic runner blocker. In that case, mark only the current row manual with the
exact browser-access blocker, then exit so the outer runner can stop safely.

Do not commit or push. The outer orchestrator owns commits.

Exit after {batch_size} row outcomes or after a systemic blocker.
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


def queued_items(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in state.get("items", []) if item.get("state") == "queued"]


def state_counts(state: dict[str, Any]) -> dict[str, int]:
    counts = {"queued": 0, "submitted": 0, "manual": 0, "archived": 0, "skipped": 0}
    for item in state.get("items", []):
        value = str(item.get("state") or "")
        if value in counts:
            counts[value] += 1
    return counts


def completed_keys(state: dict[str, Any]) -> set[str]:
    return {
        str(item.get("key") or "")
        for item in state.get("items", [])
        if item.get("state") in DONE_STATES
    }


def is_systemic_blocker(item: dict[str, Any]) -> bool:
    if item.get("state") != "manual":
        return False
    haystack = " ".join(
        str(item.get(field) or "")
        for field in ("blocker", "result", "notes")
    ).lower()
    return any(term in haystack for term in SYSTEMIC_BLOCKER_TERMS)


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)[:80] or "batch"


def child_prompt(batch_size: int) -> str:
    return BATCH_PROMPT.format(batch_size=batch_size)


def run_codex_batch(
    *,
    batch_number: int,
    batch_size: int,
    model: str,
    timeout_s: int,
    child_sandbox: str,
    dry_run: bool,
) -> tuple[int, str, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"batch_{batch_number:03d}_{safe_filename(now_iso())}.txt"
    cmd = [
        "codex",
        "exec",
        "--ephemeral",
        "--cd",
        str(ROOT),
        "--sandbox",
        child_sandbox,
        "-m",
        model,
        "-o",
        str(output_file),
        child_prompt(batch_size),
    ]
    if dry_run:
        print("  dry run command:")
        print("  " + " ".join(cmd[:10]) + " ...")
        return 0, "dry-run", output_file
    try:
        result = subprocess.run(cmd, timeout=timeout_s, capture_output=True, text=True)
        combined = (result.stdout or "") + (result.stderr or "")
        if combined and not output_file.exists():
            output_file.write_text(combined, encoding="utf-8")
        elif combined:
            with output_file.open("a", encoding="utf-8") as handle:
                handle.write("\n\n--- codex exec stdout/stderr ---\n")
                handle.write(combined)
        return result.returncode, combined, output_file
    except subprocess.TimeoutExpired as exc:
        message = f"timeout after {timeout_s}s"
        if exc.stdout:
            message += f"\n{exc.stdout}"
        if exc.stderr:
            message += f"\n{exc.stderr}"
        output_file.write_text(message, encoding="utf-8")
        return -1, message, output_file


def commit_and_push(*, push: bool, message: str) -> bool:
    paths = [
        "application-trackers/applications.md",
        "application-visualizer/src/data/tracker-data.json",
    ]
    add = subprocess.run(["git", "-C", str(ROOT), "add", *paths], capture_output=True, text=True)
    if add.returncode != 0:
        print(f"  git add failed: {add.stderr.strip()}")
        return False
    diff = subprocess.run(["git", "-C", str(ROOT), "diff", "--cached", "--quiet"], capture_output=True)
    if diff.returncode == 0:
        print("  Nothing staged for tracker/cache; skipping commit.")
        return False
    commit = subprocess.run(
        ["git", "-C", str(ROOT), "commit", "-m", message],
        capture_output=True,
        text=True,
    )
    if commit.returncode != 0:
        print(f"  git commit failed: {commit.stderr.strip()}")
        return False
    print(f"  committed: {message}")
    if push:
        pushed = subprocess.run(["git", "-C", str(ROOT), "push", "origin", "main"], capture_output=True, text=True)
        if pushed.returncode != 0:
            print(f"  git push failed: {pushed.stderr.strip()}")
            return False
        print("  pushed origin/main")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Rotate fresh Codex CLI parents through application batches.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Rows per fresh Codex process")
    parser.add_argument("--max-batches", type=int, default=0, help="Stop after N batches; 0 drains the queue")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model for codex exec (default: {DEFAULT_MODEL})")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S, help="Per-batch timeout in seconds")
    parser.add_argument(
        "--child-sandbox",
        choices=("read-only", "workspace-write", "danger-full-access"),
        default=DEFAULT_CHILD_SANDBOX,
        help=f"Sandbox for each fresh Codex process (default: {DEFAULT_CHILD_SANDBOX})",
    )
    parser.add_argument("--no-commit", action="store_true", help="Skip auto-commit every 5 confirmed submissions")
    parser.add_argument("--no-push", action="store_true", help="Commit but do not push")
    parser.add_argument("--dry-run", action="store_true", help="Print the batches without invoking codex exec")
    args = parser.parse_args()

    if args.batch_size < 1:
        raise SystemExit("--batch-size must be >= 1")

    state = load_state()
    counts = state_counts(state)
    print(
        "finish-app-script rotating batch runner | "
        f"queued: {counts['queued']} | batch-size: {args.batch_size} | "
        f"model: {args.model} | timeout: {args.timeout}s"
    )

    batch_number = 0
    submitted_since_commit = 0
    summary: list[str] = []

    while True:
        before = load_state()
        pending = queued_items(before)
        if not pending:
            print("\nQueue drained.")
            break
        if args.max_batches and batch_number >= args.max_batches:
            print(f"\nReached --max-batches {args.max_batches}, stopping.")
            break

        batch_number += 1
        batch_preview = pending[: args.batch_size]
        print(f"\nBatch {batch_number}:")
        for item in batch_preview:
            print(f"  - {item.get('company')} | {item.get('role')} | {item.get('key')}")

        before_done = completed_keys(before)
        before_submitted = state_counts(before)["submitted"]
        started = time.time()
        rc, output, output_file = run_codex_batch(
            batch_number=batch_number,
            batch_size=args.batch_size,
            model=args.model,
            timeout_s=args.timeout,
            child_sandbox=args.child_sandbox,
            dry_run=args.dry_run,
        )
        elapsed = time.time() - started
        after = load_state()
        after_counts = state_counts(after)
        after_done = completed_keys(after)
        newly_done = after_done - before_done
        new_submitted = max(0, after_counts["submitted"] - before_submitted)
        submitted_since_commit += new_submitted

        print(f"  exit rc={rc} after {elapsed:.0f}s | output: {output_file}")
        if newly_done:
            by_key = {str(item.get("key") or ""): item for item in after.get("items", [])}
            systemic_blocked = False
            for key in sorted(newly_done):
                item = by_key.get(key, {})
                state_value = item.get("state")
                blocker = item.get("blocker") or item.get("result") or ""
                line = f"{item.get('company')} | {state_value}"
                if blocker:
                    line += f" | {blocker}"
                summary.append(line)
                print(f"  {line}")
                systemic_blocked = systemic_blocked or is_systemic_blocker(item)
            if systemic_blocked:
                print("  systemic browser/Computer Use blocker detected; stopping before launching another batch.")
                break
        else:
            tail = output.strip().splitlines()[-3:]
            print("  no state progress detected")
            if tail:
                print("  last output:")
                for line in tail:
                    print(f"    {line}")
            break

        if rc != 0:
            print("  child exited non-zero; stopping for inspection.")
            break

        if not args.no_commit and submitted_since_commit >= 5:
            today = dt.date.today().isoformat()
            print(f"\nCommitting {submitted_since_commit} submitted application update(s)...")
            commit_and_push(
                push=not args.no_push,
                message=f"Apply: {submitted_since_commit} confirmed submissions {today}",
            )
            submitted_since_commit = 0

    if not args.no_commit and submitted_since_commit:
        today = dt.date.today().isoformat()
        print(f"\nFinal commit for {submitted_since_commit} submitted application update(s)...")
        commit_and_push(
            push=not args.no_push,
            message=f"Apply: {submitted_since_commit} confirmed submissions {today}",
        )

    final_counts = state_counts(load_state())
    print("\nSummary")
    print("=" * 7)
    print(
        f"queued={final_counts['queued']} submitted={final_counts['submitted']} "
        f"manual={final_counts['manual']} archived={final_counts['archived']} skipped={final_counts['skipped']}"
    )
    for line in summary:
        print(f"  - {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
