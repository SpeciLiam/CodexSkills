---
name: conduct-drain
description: Claude-conducted, Codex-executed application drain. Claude is the conductor — it builds and audits the queue, drains it in small bounded batches of Codex CLI workers (reusing finish-app-script's run_queue.py), runs a reasoning checkpoint between every batch to catch tracker corruption and systemic browser failures, gates the shared git push, and reconciles the tracker at the end. Use when the user says `$conduct-drain`, "conduct the drain", "drain my applications with review", or wants the long application drain run with Claude judgment at the seams instead of an unattended Python loop.
---

# Conduct-Drain

A Claude + Codex pairing for the long application drain. Same end goal as
`finish-app-script` — submit ready tracker rows — but instead of an unattended
Python loop spawning workers until a 3-manual circuit breaker trips, **Claude
conducts**: it reasons at the seams between small bounded batches of Codex
workers.

- **Codex workers** (via `finish-app-script/scripts/run_queue.py`) own the grind:
  one fresh `codex exec` process per application, Chrome plugin / browser work,
  form filling, submission, per-row state writeback. Unchanged from
  `finish-app-script`.
- **Claude (this skill)** owns judgment: queue audit before, a checkpoint review
  after every batch, systemic-failure detection, push gating, and final
  reconciliation.

The point is consistency on long runs. Each agent stays context-bounded: workers
see one application then exit; Claude only ever reads the compact run-state file
and outcome tails between batches, never the raw worker transcripts (it may open
one specific `/tmp/fa_script_outputs/<key>.txt` when investigating an anomaly).

## Two Modes

This skill runs in one of two modes. Pick based on how the user invokes it.

- **Attended (default).** `$conduct-drain` with no mode word, or anything like
  "conduct the drain", "run it with review", "I'm watching". Claude pauses at
  the human gates: it surfaces FRQ drafts for approval and runs `safety-gate` +
  asks before pushing. Use when the user is present and wants control.
- **Unattended / overnight.** `$conduct-drain overnight` / `auto` / `unattended`,
  or anything like "run it while I sleep", "just do everything", "don't ask me".
  Claude makes every decision itself, auto-pushes each batch, and only stops on
  systemic failure. See **Unattended / Overnight Mode** below.

The loop below is the same for both; the mode only changes the push behavior and
whether Claude pauses for the human (steps 2 and 4).

## When To Use

Use `conduct-drain` instead of `finish-app-script` when you want Claude in the
loop reviewing outcomes — typically for a large queue, after a string of flaky
runs, or when tracker integrity matters more than raw speed. Use plain
`finish-app-script` when you just want the fastest unattended drain.

## The Loop

Drive this loop yourself (Claude). Do not call `run_monitored_batches.py` — it
auto-restarts and would skip your checkpoint. Call the lower-level
`run_queue.py` with `--max-rows` equal to the batch size so control returns to
you after each batch.

### 1. Plan — build and audit the queue

```bash
python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py
python3 skills/finish-app-script/scripts/build_queue.py
```

Read `/tmp/fa_script_run_state.json`. Audit the queued rows before any worker
runs:

- Obvious duplicate postings (same company + role + URL) — flag, don't queue twice.
- Rows whose `resumePdf` path is missing on disk — flag; a worker can't attach it.
- Anything that looks mis-queued (wrong company, dead URL pattern).

Report the queue size and anything you dropped or flagged. Do not silently
rewrite the state file beyond removing clear duplicates.

### 2. Execute one bounded batch (Codex, no Claude context cost)

Default batch size is 5. Pass `--no-push` so the shared git push stays under
Claude's control; local commits are fine (recoverable).

```bash
python3 skills/finish-app-script/scripts/run_queue.py --max-rows 5 --no-push
```

This spawns up to 5 fresh Codex workers, one per application, then returns.

### 3. Checkpoint — review the batch (Claude)

Re-read `/tmp/fa_script_run_state.json` and inspect the rows that changed since
the last checkpoint. Judge, in order:

- **Systemic browser failure.** If multiple rows in the batch went `manual` with
  blockers mentioning the Chrome plugin, automation permission, auth/login loss,
  or timeouts, treat it as a systemic failure — **stop and tell Liam**, do not
  relaunch into the same broken browser state. (This is where you replace
  `run_queue.py`'s blind circuit-breaker relaunch with judgment.)
- **Tracker integrity.** Spot-check that rows now marked `submitted` carry
  `confirmationEvidence`. A `submitted` row with no confirmation evidence is
  suspect — flag it and, if needed, read that row's worker output to confirm.
- **Review queue.** Collect rows left `manual` with FRQ drafts or
  `awaiting Liam approval`. Surface the exact questions and drafts so Liam can
  approve in chat; approved answers get picked up on a later batch.
- **Drift / wrong-resume risk.** If a worker submitted something that looks
  low-confidence or attached the wrong resume, flag it explicitly.

Then decide: **continue** (loop to step 2 for the next batch), **pause** (hand
specific questions back to Liam), or **abort** (systemic failure).

### 4. Gate the push (Claude)

When you have a batch of confirmed submissions and intend to push, run the
`safety-gate` subagent first, then confirm with Liam before pushing. Pushing is a
shared/external action and stays human-confirmed per repo safety rules.

```bash
git push   # only after safety-gate + Liam approval
```

### 5. Reconcile and report

When the queue is drained (or a checkpoint stopped the run), confirm the tracker
and visualizer cache reflect every confirmed submission:

```bash
python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py
```

Final summary: confirmed submissions, manual rows with exact blockers, FRQ drafts
awaiting approval, archived rows, anything flagged for integrity, and what was
pushed.

## Unattended / Overnight Mode

When the user wants to "run it while I sleep" / do everything without being
asked, run the same loop with these policy changes — make every decision
autonomously and never stop to ask:

- **Keep the machine awake first.** Start `caffeinate -dimsu` in the background
  before the first batch; if macOS sleeps, Chrome / the plugin die mid-run. Kill
  it when the run ends.
- **Auto-submit:** unchanged — workers submit high-confidence rows; medium / FRQ
  / blocked rows are left as open tabs and logged for the morning report. Do not
  pause for FRQ approval.
- **Auto-push:** drop `--no-push` so `run_queue.py` commits and pushes tracker
  updates each batch. (Skip the `safety-gate` + human-approval push gate; it is
  the user's own repo and they opted into unattended push.)
- **Stop only on systemic failure:** when `run_queue.py`'s circuit breaker pauses
  after 3 consecutive `manual` rows, judge the blockers. If they point to a
  systemic browser break (Chrome plugin dead, auth/login lost, repeated
  timeouts), **stop and write the report** — do not relaunch into a broken
  browser. Otherwise relaunch the next batch and keep going. Individual
  manual/blocked rows are normal and never stop the run.
- **Chain automatically:** each background batch completing re-wakes the
  conductor; run the checkpoint and immediately launch the next batch. Continue
  until the queue is drained or a systemic stop. Leave a full morning report:
  submitted, manual + exact blockers, FRQ drafts awaiting approval, archived,
  integrity flags, commits/pushes, and queue remaining.

To run this mode, drop `--no-push` from step 2 and skip the step 4 human gate.

## Resuming

Run state persists in `/tmp/fa_script_run_state.json`. To continue an
interrupted conduct-drain, skip step 1 (do not rebuild) and resume the loop at
step 2 — `run_queue.py` only touches still-queued rows.

## Differences From `finish-app-script`

| | `finish-app-script` | `conduct-drain` |
|---|---|---|
| Outer orchestrator | `run_monitored_batches.py` (Python, auto-restart) | Claude, batch by batch |
| Judgment between batches | none (3-manual circuit breaker) | Claude checkpoint review |
| Systemic failure handling | blind relaunch unless fresh blocker | Claude stops and reports |
| Push | runner pushes every 5 confirmed | `--no-push`; Claude gates via safety-gate + Liam |
| Submission policy | high-confidence auto-submit | **unchanged** — workers still auto-submit high-confidence rows |

Submission behavior is intentionally identical: this skill adds review at the
seams, it does not add friction to individual high-confidence submissions.

## Future Upgrade (not in this thin version)

The biggest remaining consistency win is making workers **append-only** to
`outcomes.jsonl` and moving tracker writeback into a Claude reconciliation step
(instead of each worker calling `update_application_status.py` in place). That
eliminates the multi-writer corruption class entirely but requires changing
`run_queue.py` and the per-row prompt; do it as a separate, reviewed change.
