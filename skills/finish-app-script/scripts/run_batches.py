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
Computer Use directly for Google Chrome in this process. Use app name
"Google Chrome" or bundle id "com.google.Chrome"; do not use bare "Chrome".
Do not spawn subagents or parallel browser workers.

Process up to {batch_size} queued application rows from
/tmp/fa_script_run_state.json, then exit cleanly. Before each row, reread the
state file and pick the first items[] entry with state == "queued". Keep one
browser flow active at a time.

For each row:
- Always open a brand-new Chrome tab before navigating to the jobLink, including
  the first row in this batch. Never navigate over an existing application,
  email, search, or handoff tab.
- Keep tabs organized by perceived confidence when possible: High Confidence /
  Ready Submit, Needs Review, Hard Blocker, and Submitted / Archived. If Chrome
  tab groups are not scriptable, leave tabs ordered in that bucket sequence and
  make the outcome note clear enough for Liam to identify the bucket.
- Complete the live application with the row's resumePdf. During file upload,
  the macOS file picker may default to the previous application's file; before
  confirming any upload, verify the selected path exactly matches the current
  row's resumePdf from /tmp/fa_script_run_state.json.
- Resume/CV and Cover Letter fields are file-upload only. Never click
  "Enter manually", never paste resume or cover-letter text into an ATS form,
  and never submit with manually entered document text.
- If a Cover Letter field is present, attach a cover-letter PDF too. Look in
  the same directory as resumePdf for Liam_Van_<Company>_Cover_Letter.pdf. If
  it is missing, generate and render it before upload:
  python3 skills/resume-tailor/scripts/create_cover_letter.py --dir "<resume directory>" --company "<Company>" --role "<Role>" --why-interest "<2-3 truthful sentences grounded in the posting and Liam's projects>"
  python3 skills/resume-tailor/scripts/render_cover_letter_pdf.py --dir "<resume directory>"
  Upload the rendered cover-letter PDF by file picker, never manual text.
- If an exact resume or cover-letter PDF cannot be attached after one retry,
  leave the tab open, mark the row manual with blocker
  "Document upload failed; manual attach required", and continue.
- Submit high and medium confidence applications when every required field is
  filled truthfully from standing answers, obvious profile facts, resume,
  projects, or concise FRQ/custom written drafts. Click the final Submit/Submit
  application button, wait for a confirmation page or confirmation text,
  capture it in confirmationEvidence, and set state to "submitted". Do not
  leave a high/medium confidence application staged.
- Before clicking final Submit, make a short explicit decision: "submit is safe
  because <reason>". Base the decision on the row's confidence score: high and
  medium may submit after truthful completion; low must not submit. If a low
  confidence row has unanswered or uncertain items, mark the row manual with the
  exact item Liam needs to review and leave the tab open.
- Treat these rendered answers as guardrails before final submit: authorized to
  work in the United States = Yes; now/future sponsorship required = No;
  comfortable working onsite/hybrid/in-office in NYC or San Francisco, including
  San Francisco 5 days/week = Yes. If any present answer differs, correct it. If
  you cannot correct it, mark manual and leave the tab open.
- Medium confidence FRQ/custom written prompts are submit-capable when they can
  be answered truthfully from Liam's profile, resume, projects, and standing
  answers. Draft concise, specific, truthful answers, review them for factual
  accuracy, and submit if the only remaining uncertainty is phrasing quality.
- Low confidence rows must not be submitted. Fill safe fields, upload the
  correct resume when possible, leave the tab open at the cleanest review point,
  mark manual with the exact blocker, and continue to the next row.
- Do not stall on a final-submit decision. Once the form is as complete as it
  safely can be, either submit with confirmation evidence or mark manual and
  exit/continue. Never hover at a staged final form waiting for confidence to
  improve.
- If submitted successfully and confirmation evidence is captured, close that
  application tab before starting the next row.
- For medium confidence, submit when the only issue is a truthful FRQ/custom
  answer that you can draft accurately. If a medium row has a factual,
  eligibility, legal, location, salary, or experience uncertainty outside
  standing answers, leave the tab at the cleanest review point and mark manual
  with an exact blocker. Keep that handoff tab open even if this Codex process
  is about to exit.
- For account creation, login, SMS/authenticator 2FA, interactive CAPTCHA,
  Workday, AI-deterrent verification, or other impossible-to-complete steps,
  mark manual with the exact blocker, leave any useful partially completed tab
  open for Liam, and continue to the next queued row. These are per-row outcomes,
  not hard stops for the batch.
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

If Chrome/Computer Use itself is unavailable for a row, mark only the current
row manual with the exact browser-access blocker, then continue when possible.
Do not stop the whole batch solely because one row cannot be automated.

Do not commit or push. The outer orchestrator owns commits.

Exit after {batch_size} row outcomes.
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
        "application-trackers/outcomes.jsonl",
        "application-visualizer/src/data/tracker-data.json",
        "application-visualizer/src/data/pipeline-metrics.json",
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
        branch = subprocess.run(
            ["git", "-C", str(ROOT), "branch", "--show-current"],
            capture_output=True,
            text=True,
        )
        branch_name = branch.stdout.strip() or "HEAD"
        pushed = subprocess.run(
            ["git", "-C", str(ROOT), "push", "origin", branch_name],
            capture_output=True,
            text=True,
        )
        if pushed.returncode != 0:
            print(f"  git push failed: {pushed.stderr.strip()}")
            return False
        print(f"  pushed origin/{branch_name}")
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
    parser.add_argument("--no-commit", action="store_true", help="Skip auto-commit every 5 submitted/archived outcomes")
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
    terminal_success_since_commit = 0
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
        before_counts = state_counts(before)
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
        new_submitted = max(0, after_counts["submitted"] - before_counts["submitted"])
        new_archived = max(0, after_counts["archived"] - before_counts["archived"])
        terminal_success_since_commit += new_submitted + new_archived

        print(f"  exit rc={rc} after {elapsed:.0f}s | output: {output_file}")
        if newly_done:
            by_key = {str(item.get("key") or ""): item for item in after.get("items", [])}
            for key in sorted(newly_done):
                item = by_key.get(key, {})
                state_value = item.get("state")
                blocker = item.get("blocker") or item.get("result") or ""
                line = f"{item.get('company')} | {state_value}"
                if blocker:
                    line += f" | {blocker}"
                summary.append(line)
                print(f"  {line}")
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

        if not args.no_commit and terminal_success_since_commit >= 5:
            today = dt.date.today().isoformat()
            print(f"\nCommitting {terminal_success_since_commit} submitted/archived application outcome(s)...")
            commit_and_push(
                push=not args.no_push,
                message=f"Apply: {terminal_success_since_commit} submitted or archived outcomes {today}",
            )
            terminal_success_since_commit = 0

    if not args.no_commit and terminal_success_since_commit:
        today = dt.date.today().isoformat()
        print(f"\nFinal commit for {terminal_success_since_commit} submitted/archived application outcome(s)...")
        commit_and_push(
            push=not args.no_push,
            message=f"Apply: {terminal_success_since_commit} submitted or archived outcomes {today}",
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
