#!/usr/bin/env python3
"""Rotate fresh Codex CLI processes through small LinkedIn pipeline batches."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
STATE_PATH = Path("/tmp/linkedin_full_pipeline_state.json")
OUTPUT_DIR = Path("/tmp/linkedin_full_pipeline_batch_outputs")
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_TIMEOUT_S = 2700
DONE_STATES = {"applied", "manual", "manual_apply_needed", "archived", "skipped", "duplicate"}
SYSTEMIC_BLOCKER_TERMS = (
    "chrome computer use unavailable",
    "computer use access denied",
    "appnotfound(\"google chrome\")",
    "linkedin login unavailable",
)


BATCH_PROMPT = """\
Read skills/linkedin-full-pipeline/OPERATING_CARD.md before starting. Follow it strictly.

You are a fresh parent agent launched by the monitored LinkedIn full-pipeline runner.
Use Codex Computer Use directly for Google Chrome in this process. Do not spawn
subagents or parallel browser workers. Process up to {batch_size} NEW LinkedIn jobs,
then exit cleanly.

Durable state file: {state_path}

Before starting and before each job, reread the state file. Respect:
- runPolicy.outreachMode: if "throttled", do not send LinkedIn connection invites.
  You may still verify recruiter profiles and record notes/queued outreach.
- search.phase: start with early-career search. Widen to broad fallback only when
  early-career results are saturated with duplicates, stale roles, internships,
  wrong locations, or poor fits, and record search.saturationReason.
- runPolicy.maxJobs: stop when items with done states reach that count.

For each job:
1. Open the early-career LinkedIn search URL from state unless search.phase is
   already "broad-fallback".
2. If state.items already contains an item with state="in_progress", continue
   that exact job to a durable application outcome before selecting a new job.
   Apply the current runPolicy fields to it, including coverLetterPolicy.
3. Pick one fresh realistic SWE job in a cared-about location. Dedupe against
   application-trackers/applications.md, application-trackers/job-intake.md, and
   state.items[].jobUrl. If duplicate, append a state item with state="duplicate"
   and continue only if batch capacity remains.
4. Tailor the resume with resume-tailor, render/verify the PDF, and update the
   markdown tracker. Refresh visualizer cache after tracker edits.
5. Recruiter outreach: verify only current in-house recruiter/talent profiles at
   the target company. If outreachMode is active and LinkedIn allows Connect,
   send the <=300 char note and record it. If LinkedIn reports too many
   connection requests / weekly limit / invitations restricted, set
   runPolicy.outreachMode="throttled", record the event, and do not attempt any
   more connection sends in this run.
6. Attempt the application with the tailored resume. If the application offers
   an optional cover letter upload or text field, tailor a concise role-specific
   cover letter from the job description and Liam's resume, include it, and
   record whether it was uploaded or pasted. The cover letter content must use
   Liam Van's real name, and uploaded PDFs must be named
   Liam_Van_<Company>_Cover_Letter.pdf, never Candidate_Name_... . Missing cover
   letter fields are not blockers. Submit high-confidence routine applications
   with confirmation evidence. For low confidence, fill safe fields, leave the
   tab open at a clean review point, group/reorder Chrome tabs into High
   confidence / Low confidence when practical, and record the exact blocker. Do
   not submit Workday, CAPTCHA, account creation, SMS/authenticator 2FA, legal
   signature, or unsupported eligibility/salary commitments.
7. Append or update one item in the state file with:
   key, company, role, jobUrl, location, source, resumePdf, recruiterName,
   recruiterProfile, outreachState, coverLetterState, coverLetterPath,
   applicationConfidence, state, result, blocker, confirmationEvidence,
   updatedAt.
8. If no more usable jobs remain in both search phases, set
   search.stopRequested=true with search.saturationReason.

After each durable outcome, write the state file immediately. Exit after
{batch_size} non-duplicate application outcomes, after search.stopRequested, or
after a systemic Chrome/LinkedIn access blocker.

Do not commit or push. The outer orchestrator owns commits if needed.
"""


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        raise SystemExit(
            f"Missing run state at {STATE_PATH}. Run: "
            "python3 skills/linkedin-full-pipeline/scripts/build_run_state.py"
        )
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def done_count(state: dict[str, Any]) -> int:
    return sum(1 for item in state.get("items", []) if item.get("state") in DONE_STATES)


def submitted_count(state: dict[str, Any]) -> int:
    return sum(1 for item in state.get("items", []) if item.get("state") == "applied")


def stop_requested(state: dict[str, Any]) -> bool:
    return bool(state.get("search", {}).get("stopRequested"))


def has_systemic_blocker(state: dict[str, Any]) -> bool:
    for item in state.get("items", []):
        haystack = " ".join(str(item.get(field) or "") for field in ("blocker", "result")).lower()
        if any(term in haystack for term in SYSTEMIC_BLOCKER_TERMS):
            return True
    return False


def prompt(batch_size: int) -> str:
    return BATCH_PROMPT.format(batch_size=batch_size, state_path=STATE_PATH)


def run_child(batch_no: int, batch_size: int, model: str, timeout: int, sandbox: str, dry_run: bool) -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"batch_{batch_no:03d}_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.txt"
    cmd = [
        "codex",
        "exec",
        "--ephemeral",
        "--cd",
        str(ROOT),
        "--sandbox",
        sandbox,
        "-m",
        model,
        "-o",
        str(output_file),
        prompt(batch_size),
    ]
    print(f"\nBatch {batch_no}: output -> {output_file}")
    if dry_run:
        print("  dry run command:")
        print("  " + " ".join(cmd[:12]) + " ...")
        return 0
    try:
        result = subprocess.run(cmd, timeout=timeout, capture_output=True, text=True)
    except subprocess.TimeoutExpired as exc:
        output_file.write_text(f"timeout after {timeout}s\n{exc.stdout or ''}\n{exc.stderr or ''}", encoding="utf-8")
        return -1
    combined = (result.stdout or "") + (result.stderr or "")
    if combined:
        with output_file.open("a", encoding="utf-8") as handle:
            handle.write("\n\n--- codex exec stdout/stderr ---\n")
            handle.write(combined)
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run monitored LinkedIn full-pipeline child batches.")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--max-batches", type=int, default=0)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--child-sandbox", default="danger-full-access", choices=("read-only", "workspace-write", "danger-full-access"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    batch_no = 0
    while True:
        state = load_state()
        max_jobs = int(state.get("runPolicy", {}).get("maxJobs") or 0)
        before_done = done_count(state)
        if stop_requested(state):
            print("Search saturation/stop requested; no more batches.")
            return 0
        if max_jobs and before_done >= max_jobs:
            print(f"Reached max jobs: {before_done}/{max_jobs}")
            return 0
        if has_systemic_blocker(state):
            print("Systemic browser/LinkedIn blocker detected; stopping.")
            return 2
        if args.max_batches and batch_no >= args.max_batches:
            print("Stopped because --max-batches was reached.")
            return 0

        batch_no += 1
        rc = run_child(batch_no, args.batch_size, args.model, args.timeout, args.child_sandbox, args.dry_run)
        after = load_state()
        after_done = done_count(after)
        print(
            f"Progress: done {before_done} -> {after_done}; "
            f"applied={submitted_count(after)}; outreachMode={after.get('runPolicy', {}).get('outreachMode')}"
        )
        if args.dry_run:
            return 0
        if stop_requested(after) or (max_jobs and after_done >= max_jobs):
            return rc
        if has_systemic_blocker(after):
            return rc or 2
        if after_done <= before_done and rc != 0:
            return rc


if __name__ == "__main__":
    raise SystemExit(main())
