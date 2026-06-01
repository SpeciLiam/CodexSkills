#!/usr/bin/env python3
"""Run fresh Claude or Codex workers through the LinkedIn apply-all queue."""

from __future__ import annotations

import argparse
import atexit
import datetime as dt
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
STATE_PATH = Path("/tmp/linkedin_apply_all_state.json")
OUTPUT_DIR = Path("/tmp/linkedin_apply_all_worker_outputs")
LOCK_PATH = Path("/tmp/linkedin_apply_all_worker.lock")
DONE_STATES = {
    "submitted",
    "applied",
    "manual",
    "manual_apply_needed",
    "archived",
    "skipped",
    "duplicate",
    "queued_for_tailoring",
}
SYSTEMIC_BLOCKER_TERMS = (
    "chrome computer use unavailable",
    "computer use access denied",
    "appnotfound(\"google chrome\")",
    "linkedin login unavailable",
    "linkedin rate limit",
    "account restricted",
)


WORKER_PROMPT = """\
Read skills/linkedin-apply-all/OPERATING_CARD.md before starting. Follow it strictly.

You are a fresh {worker} worker launched by the LinkedIn apply-all queue runner.
Use the authenticated Liam Chrome profile for live LinkedIn/application work.
Prefer the Chrome extension backend when available. If Chrome extension
discovery fails but the Google Chrome app is visible, use Computer Use as the
sole browser actor for this worker. Do not spawn subagents, monitors, parallel
browser tools, or a separate resume-tailor worker. You are the only active
worker. Process up to {batch_size} LinkedIn application outcome(s), then exit
cleanly.

Durable state file: {state_path}

Before starting and before each job, reread the state file. Respect:
- runPolicy.mode must be "linkedin-apply-all" applications-only.
- runPolicy.worker is "{worker}".
- runPolicy.missingResumePolicy controls what to do when a realistic new posting
  lacks a tailored resume. Default "tailor" means run a bounded resume-tailor
  workflow yourself for the exact posting, refresh tracker/cache, update the
  state item with the new resume path, then continue the application with that
  resume. Do not run recruiter outreach or the full sourcing pipeline.
- runPolicy.outreachAllowed=false means no recruiter search and no LinkedIn
  connection invites.
- Read skills/linkedin-easy-apply-nodriver/references/application-defaults.md
  and, when present, skills/linkedin-apply-all/private-application-defaults.md
  before marking routine questions, login/account creation, 2FA, salary, phone,
  legal defaults, or Workday flow as blockers. Do not print or commit private
  credentials or verification codes.
- Browser access rule: exactly one browser access method may be active. If you
  fall back from Chrome extension to Computer Use, do not keep trying the Chrome
  extension in parallel.
- search.url is the LinkedIn search to keep open. It already includes the chosen
  f_TPR freshness window.
- search.currentResultIndex and visitedJobUrls are durable cursor hints. Update
  them after each inspected card.
- If state contains an item with state "needs_tailoring", process that item
  before opening the next LinkedIn card by running the bounded resume-tailor
  step for its exact jobUrl.
- If state contains an item with state "tailored" or "in_progress_tailoring"
  and a valid resumePdf, process that item before opening the next LinkedIn card,
  even if its jobUrl is already in visitedJobUrls.
- If state contains an item with state "revisit_skipped", process that skipped
  item before opening the next LinkedIn card. Liam asked to go through all
  results, so previous location, staffing/vendor, weak-fit, low-salary,
  placement-funnel, and stack-mismatch skips are not terminal. Attempt the
  application path with truthful standing answers. Only stop short for hard
  blockers: duplicate/already handled, closed/unavailable posting, required
  active clearance Liam does not have, impossible date/eligibility requirements,
  CAPTCHA/bot checks, failed login/2FA/account creation after defaults,
  unsupported legal answers, or a required answer that cannot be truthfully
  provided.
- Stop only if search.stopRequested, maxJobs is reached, the manual circuit
  breaker is hit, or a systemic LinkedIn/Chrome/auth/rate-limit blocker appears.

Per result, in order:
1. Open or return to search.url in Chrome. Inspect the next unvisited visible
   LinkedIn job card at/after search.currentResultIndex.
2. Capture title, company, location, LinkedIn URL/id, posted age, apply mode,
   and salary/applicant count if visible. Add the URL/id to visitedJobUrls and
   append/update a state item before application work.
3. Dedupe against application-trackers/applications.md, application-trackers/job-intake.md,
   and state items by Posting Key, LinkedIn job id, canonical URL, ATS URL, and
   normalized company + title. If already handled/completed, mark duplicate and
   continue if capacity remains.
4. In normal mode, skip obvious bad fits: non-SWE,
   senior/staff/principal/manager, sales/support, internship-only, closed/stale,
   or outside Liam's cared-about locations. If runPolicy.noSkipAllResults is
   true, do not skip for location, staffing/vendor source, weak fit, low salary,
   placement-funnel language, or stack mismatch; attempt the application path
   anyway using truthful standing answers.
5. If a valid tailored resume exists for this exact posting, apply with it. If
   not, follow runPolicy.missingResumePolicy exactly:
  - "tailor": record the item as in_progress_tailoring, run the bounded
    resume-tailor workflow yourself for the exact LinkedIn/ATS posting, refresh
    the tracker/cache, update the item with resumePdf and state tailored, then
    continue this same worker into the application with the new resume.
   - "queue_for_tailoring": mark queued_for_tailoring with captured job details
     and continue.
   - "skip": mark skipped with the missing-resume reason and continue.
6. Attempt the application using finish-applications guardrails. Verify LinkedIn
   Easy Apply email is liamvanpj@gmail.com. Workday applications are allowed but
   slower; attempt them one at a time and submit only with high confidence.
   Do not solve CAPTCHA, bypass bot checks, guess unsupported legal/eligibility
   answers, or submit when standing defaults do not cover the required answer.
7. Record one durable item outcome with:
   key, company, role, jobUrl, linkedinJobId, location, source, applyMode,
   resumePdf, applicationConfidence, state, result, blocker,
   confirmationEvidence, updatedAt.
8. Update application-trackers/applications.md and generated visualizer cache
   only when source-of-truth status changed. Use existing status/outcome helpers
   when they are already part of the application workflow.
9. If no more usable jobs are visible/loadable, set search.stopRequested=true
   with search.saturationReason.

Exit after {batch_size} non-duplicate application outcome(s), after search
saturation, after the manual circuit breaker, or after a systemic blocker.
Do not commit or push.
"""


def now_tag() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        raise SystemExit(
            f"Missing run state at {STATE_PATH}. Run: "
            "python3 skills/linkedin-apply-all/scripts/build_run_state.py"
        )
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def acquire_worker_lock() -> None:
    while True:
        try:
            fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as lock:
                lock.write(f"{os.getpid()}\n")
            atexit.register(release_worker_lock)
            return
        except FileExistsError:
            try:
                pid_text = LOCK_PATH.read_text(encoding="utf-8").strip()
                existing_pid = int(pid_text)
                os.kill(existing_pid, 0)
            except (ValueError, ProcessLookupError, FileNotFoundError):
                try:
                    LOCK_PATH.unlink()
                except FileNotFoundError:
                    pass
                continue
            except PermissionError:
                pass
            raise SystemExit(f"Another linkedin-apply-all worker is already active; lock: {LOCK_PATH}")


def release_worker_lock() -> None:
    try:
        if LOCK_PATH.read_text(encoding="utf-8").strip() == str(os.getpid()):
            LOCK_PATH.unlink()
    except FileNotFoundError:
        pass


def done_count(state: dict[str, Any]) -> int:
    return sum(1 for item in state.get("items", []) if item.get("state") in DONE_STATES)


def progress_count(state: dict[str, Any]) -> int:
    return done_count(state) + len(state.get("events", []))


def submitted_count(state: dict[str, Any]) -> int:
    return sum(1 for item in state.get("items", []) if item.get("state") in {"submitted", "applied"})


def manual_count(state: dict[str, Any]) -> int:
    return sum(1 for item in state.get("items", []) if item.get("state") in {"manual", "manual_apply_needed"})


def stop_requested(state: dict[str, Any]) -> bool:
    return bool(state.get("search", {}).get("stopRequested"))


def hit_manual_circuit_breaker(state: dict[str, Any]) -> bool:
    limit = int(state.get("runPolicy", {}).get("manualCircuitBreaker") or 0)
    return bool(limit and manual_count(state) >= limit)


def has_systemic_blocker(state: dict[str, Any]) -> bool:
    for item in state.get("items", []):
        haystack = " ".join(str(item.get(field) or "") for field in ("blocker", "result")).lower()
        if any(term in haystack for term in SYSTEMIC_BLOCKER_TERMS):
            return True
    return False


def prompt(worker: str, batch_size: int) -> str:
    return WORKER_PROMPT.format(worker=worker, batch_size=batch_size, state_path=STATE_PATH)


def codex_cmd(prompt_text: str, output_file: Path, model: str | None, sandbox: str, reasoning: str | None) -> list[str]:
    cmd = [
        "codex",
        "exec",
        "--ephemeral",
        "--cd",
        str(ROOT),
        "--sandbox",
        sandbox,
        "-o",
        str(output_file),
    ]
    # Model: when --codex-model is unset we deliberately omit -m so codex uses the
    # config.toml default, which Liam keeps pointed at the latest codex model.
    if model:
        cmd.extend(["-m", model])
    # Reasoning effort: force it explicitly so workers run at the intended
    # intelligence even if config.toml is absent/overridden. Default "medium".
    if reasoning:
        cmd.extend(["-c", f"model_reasoning_effort={reasoning}"])
    cmd.append(prompt_text)
    return cmd


def claude_cmd(model: str | None, permission: str) -> list[str]:
    cmd = ["claude", "-p", "--permission-mode", permission, "--add-dir", str(ROOT)]
    if model:
        cmd.extend(["--model", model])
    return cmd


def run_worker(batch_no: int, worker: str, batch_size: int, args: argparse.Namespace) -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"{worker}_{batch_no:03d}_{now_tag()}.txt"
    prompt_text = prompt(worker, batch_size)
    if worker == "codex":
        cmd = codex_cmd(prompt_text, output_file, args.codex_model, args.child_sandbox, args.codex_reasoning)
        stdin_data = None
    else:
        cmd = claude_cmd(args.claude_model, args.claude_permission)
        stdin_data = prompt_text

    print(f"\nWorker {batch_no} ({worker}): output -> {output_file}")
    if args.dry_run:
        print("  dry run command:")
        print("  " + " ".join(cmd[:14]) + (" ..." if len(cmd) > 14 else ""))
        print(f"  prompt preview: {prompt_text.splitlines()[0]}")
        return 0

    if not shutil.which(worker):
        message = f"missing worker CLI: {worker}"
        print(message)
        output_file.write_text(message + "\n", encoding="utf-8")
        return 127

    try:
        result = subprocess.run(
            cmd,
            input=stdin_data,
            timeout=args.timeout,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
    except subprocess.TimeoutExpired as exc:
        output_file.write_text(f"timeout after {args.timeout}s\n{exc.stdout or ''}\n{exc.stderr or ''}", encoding="utf-8")
        return -1

    combined = (result.stdout or "") + (result.stderr or "")
    output_file.write_text(combined, encoding="utf-8")
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LinkedIn apply-all queue workers.")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--worker", choices=("codex", "claude"), help="Override worker in state")
    parser.add_argument("--codex-model")
    parser.add_argument("--codex-reasoning", default="medium", help="codex model_reasoning_effort (default: medium)")
    parser.add_argument("--claude-model")
    parser.add_argument("--claude-permission", default="acceptEdits")
    parser.add_argument("--timeout", type=int, default=2700)
    parser.add_argument("--child-sandbox", default="danger-full-access", choices=("read-only", "workspace-write", "danger-full-access"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    acquire_worker_lock()

    batch_no = 0
    while True:
        state = load_state()
        worker = args.worker or state.get("runPolicy", {}).get("worker") or "codex"
        max_jobs = int(state.get("runPolicy", {}).get("maxJobs") or 0)
        before_done = done_count(state)
        before_progress = progress_count(state)
        if stop_requested(state):
            print("Search saturation/stop requested; no more workers.")
            return 0
        if max_jobs and before_done >= max_jobs:
            print(f"Reached max jobs: {before_done}/{max_jobs}")
            return 0
        if hit_manual_circuit_breaker(state):
            print("Manual blocker circuit breaker reached.")
            return 3
        if has_systemic_blocker(state):
            print("Systemic browser/LinkedIn blocker detected; stopping.")
            return 2
        if args.max_workers and batch_no >= args.max_workers:
            print("Stopped because --max-workers was reached.")
            return 0

        batch_no += 1
        rc = run_worker(batch_no, worker, args.batch_size, args)
        after = load_state()
        after_done = done_count(after)
        after_progress = progress_count(after)
        print(
            f"Progress: done {before_done} -> {after_done}; "
            f"submitted={submitted_count(after)}; manual={manual_count(after)}; worker={worker}"
        )
        if args.dry_run:
            return 0
        if stop_requested(after) or (max_jobs and after_done >= max_jobs):
            return rc
        if hit_manual_circuit_breaker(after):
            return rc or 3
        if has_systemic_blocker(after):
            return rc or 2
        if after_progress <= before_progress:
            return rc or 4


if __name__ == "__main__":
    raise SystemExit(main())
