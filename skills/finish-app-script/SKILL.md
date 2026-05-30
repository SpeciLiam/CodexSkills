---
name: finish-app-script
description: Drain Liam's tailored-resume application queue from a phone-friendly command. Build `/tmp/fa_script_run_state.json`, then launch one fresh Codex or Claude worker per application so each worker attempts one form, submits and closes the tab when high-confidence, leaves a prepared handoff tab on true blockers, updates tracker/cache, and exits. Use when the user says `$finish-app-script`, "run finish app script", "drain my application queue", or wants applications completed without context overflow.
---

# Finish-App-Script

A reliability-focused parallel of `finish-applications`. Same goal — submit ready tracker rows — but uses an outer orchestrator to launch a fresh Codex or Claude worker for exactly one application at a time.

## Default Invocation

When the user invokes `$finish-app-script` or asks to run this skill from chat,
do this without asking for extra confirmation:

```bash
python3 skills/finish-app-script/scripts/run_monitored_batches.py
```

Use `run_monitored_batches.py` by default for live browser work. Despite the
historical name, it now refreshes the tracker cache, builds
`/tmp/fa_script_run_state.json`, runs `run_queue.py`, and restarts the
per-application worker orchestrator if it stops while queued rows remain. The
inner runner may pause after three consecutive manual outcomes; the monitor
should treat that as a relaunch point, not as completion, unless the just-finished
run created a fresh systemic Chrome plugin / browser blocker. Monitor its terminal
output while it runs. If the assistant turn is interrupted or the shell
session disappears, inspect `/tmp/fa_script_run_state.json`; when queued rows
remain and no `run_queue.py`, `codex exec`, or `claude -p` worker process is
active, resume with:

```bash
python3 skills/finish-app-script/scripts/run_monitored_batches.py --resume
```

Do not pass `--no-commit` or `--no-push` unless the user explicitly asks.
`run_queue.py` owns commits and pushes, including final commits for confirmed
submissions.

## Browser Profiles

- **Job sourcing / LinkedIn search:** Ben Chrome profile,
  `bendov1010@gmail.com`, profile directory `Profile 1`, usually through
  Nodriver.
- **Actual applications / ATS forms:** Liam Chrome profile,
  `liamvanpj@gmail.com`, profile directory `Default`, through the installed
  Codex Chrome plugin first. This keeps Liam's real cookies, saved logins,
  existing tabs, extension-backed uploads, and ATS portal state. Before filling
  or submitting any application, verify the active Chrome window is Liam's
  profile, not Ben's. If needed, open it with:

```bash
open -na "Google Chrome" --args --profile-directory="Default"
```

Use Computer Use only as the fallback when the Chrome plugin cannot communicate
with Chrome or cannot operate the current ATS page.

Default queue behavior includes all not-applied rows that pass the script's
basic filters, including rows previously labeled true manual or Workday. Every
queued row must get one worker attempt. Those rows are queued as low-confidence
live-browser attempts so the agent can fill safe fields and answerable FRQs,
then leave the tab open with a precise blocker or review note. Final submission
is still allowed only for high-confidence rows.
If the Chrome plugin cannot communicate with Chrome and Chrome/Computer Use
also times out or is unavailable, stop the run as a systemic browser blocker
instead of marking the rest of the queue manual. If Firefox is responsive
through Computer Use, future batches may use Firefox as the fallback browser so
the queue can continue without losing the high-confidence-only submission gate.
Email 2FA, verification codes, and magic links sent to liamvanpj@gmail.com are
not blockers; the one-application worker should use Gmail access to retrieve the code or
open the link and continue. Only SMS/authenticator-app 2FA, missing/expired
emails, or account-creation/legal gates should become manual blockers.
For native macOS file uploads, use Cmd+Shift+G with the exact absolute PDF path
from the row state, then Return/Open, and verify the rendered attached filename.
Do not trust folder-click navigation when the picker remembers a previous
application's directory or stale file.
If the Chrome plugin reports that file upload is blocked, leave the tab open and
tell Liam to enable file URL access for the Codex Chrome Extension in
`chrome://extensions`.
For Greenhouse upload widgets, click the nested `Browse...` button inside the
Resume/CV field rather than the outer `Attach` control; the
outer control can leave `Open` disabled even when a PDF is selected.
If Firefox selects the exact existing PDF but leaves the native picker `Open`
button disabled, treat that as a Firefox upload bug, not a missing-file blocker:
retry the same public ATS form in Safari using the same nested `Browse...` and
Cmd+Shift+G exact-path flow before marking the row manual.
For known upload-redo rows whose notes or blocker mention `Document upload
failed`, `upload-error redo`, or `Firefox picker`, start the document upload in
Safari instead of spending the retry on Firefox. Safari has been verified on
Uare.ai Greenhouse for resume PDFs.

## Tab Confidence Grouping

During live browser runs, keep open application tabs organized by perceived
handoff confidence:

- **High Confidence / Ready Submit**: fully completed tabs where every required
  answer is covered by standing answers, resume/profile evidence, grounded FRQs,
  or routine boilerplate acknowledgements; critical rendered answers are
  verified, and only final submission/confirmation remains.
- **Needs Review**: tabs with one or more medium-confidence answers, free
  response drafts, eligibility/location/salary uncertainty, or required choices
  that Liam should inspect.
- **Hard Blocker**: login/account creation, SMS/authenticator 2FA, CAPTCHA,
  Workday account/profile gates after a best-effort attempt, non-routine legal
  signature/attestation or contract terms, AI-deterrent verification, or other
  true blockers.
- **Submitted / Archived**: confirmation tabs, already-submitted portals, closed
  postings, mismatched redirects, and not-found pages.

If Chrome tab groups are available through UI automation, place tabs into those
groups. If tab groups are not scriptable from the current environment, use the
closest non-destructive fallback: reorder tabs into the same sequence and keep a
short written map in the run notes or final response.

## How To Run

```bash
# Refresh the tracker cache
python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py

# Build the queue (writes /tmp/fa_script_run_state.json)
python3 skills/finish-app-script/scripts/build_queue.py

# Preferred for live browser application work: launch one fresh worker per
# application, restarting if the runner stops.
python3 skills/finish-app-script/scripts/run_monitored_batches.py

# Resume an existing run state without rebuilding the queue.
python3 skills/finish-app-script/scripts/run_monitored_batches.py --resume

# Lower-level per-application runner used by the monitor.
python3 skills/finish-app-script/scripts/run_queue.py
```

`run_monitored_batches.py` flags:

- `--resume` — skip refresh/build and continue `/tmp/fa_script_run_state.json`
- `--max-restarts N` — retry stopped runs with queued rows remaining (default `0` = keep trying)
- `--restart-sleep SECONDS` — wait before retrying (default `10`)
- `--max-rows N` — stop after N one-application workers (testing)
- `--max-batches N` — legacy alias for `--max-rows`
- `--batch-size N` — accepted for compatibility; ignored because each worker owns one application
- `--worker-agent codex|claude` — choose which CLI performs each row (default `codex`)
- all normal `run_queue.py` flags below are forwarded where applicable

`run_queue.py` flags:

- `--worker-agent codex|claude` — choose which CLI performs each row (default `codex`)
- `--max-rows N` — stop after N one-application workers (testing)
- `--model MODEL` — override default `gpt-5.5`
- `--reasoning-effort EFFORT` — child reasoning effort (default `medium`)
- `--timeout SECONDS` — per-application timeout (default 1200s = 20 min)
- `--child-sandbox MODE` — sandbox for each one-application worker (default `danger-full-access`)
- `--no-commit` — skip auto-commit every 5 confirmed submissions
- `--no-push` — commit but don't push
- `--dry-run` — print what would be spawned without invoking a worker

## Architecture

### Per-Application Worker Mode (`run_queue.py`)

```
run_queue.py (outer orchestrator)
  ├── reads /tmp/fa_script_run_state.json
  └── while queued rows remain:
        ├── selects the first queued row
        ├── spawns one fresh Codex or Claude worker:
        │     codex exec --cd $REPO --sandbox danger-full-access ...
        │     # or: claude -p --permission-mode acceptEdits --add-dir $REPO
        ├── that worker owns Chrome plugin / browser work for exactly one application
        │   using Liam's Chrome profile (`Default`, `liamvanpj@gmail.com`)
        ├── worker attempts every queued row as far as safely possible,
        │   submits/closes if high-confidence,
        │   or leaves one prepared handoff tab open if manual, writes state, exits
        │   (the next row starts from a new tab; never reuse a blocked/review tab)
        ├── outer orchestrator re-reads state and summarizes progress
        └── commits + pushes every 5 confirmed submissions
```

This is the preferred live-browser mode. Each spawned agent is a fresh process
with no context history. It reads `OPERATING_CARD.md`, applies to one job,
writes outcome to the state file, and exits.

## Why This Architecture

| Pain point | Why this fixes it |
|---|---|
| Context overflow | Each worker sees only one application before the CLI process exits |
| Browser flakiness | Chrome plugin is tried first; each fallback browser attempt is isolated to one row and one state writeback |
| FRQ blocking the queue | Draft-and-leave-open enforced per row when FRQ review is useful; orchestrator continues |
| Single-agent drift | The submission rule lives in the prompt itself, can't degrade |

## Bug Fixes vs `finish-applications`

`build_queue.py` corrects three behaviors in the original `build_application_queue.py`:

1. **`"not automation-accessible"` is retryable**, not a true blocker. Past notes from environment failures (denied Chrome automation permission) used to permanently lock those rows; they re-enter the queue now.
2. **Manual-Apply-Needed rows with no specific note are retryable.** Original `true_manual_reason()` returned a generic non-empty fallback that forced `action=manual`. Returns `""` here so they get `action=retry/apply`.
3. **FRQ terms reduce confidence, not block the row.** `"free response"`, `"free-response"`, `"custom"` moved out of `TRUE_MANUAL_BLOCKERS` into a new `CONFIDENCE_REDUCERS` list (`-20` score impact, pushes to medium band so the agent drafts the answer, leaves the tab open for review when useful, and continues).

## Per-Row Prompt Template

The orchestrator builds this for each spawned agent. Keep it tight; do not bloat with full SKILL contents — the agent reads `OPERATING_CARD.md` for rules.

```
Read skills/finish-app-script/OPERATING_CARD.md before starting. Follow it strictly.

You are completing ONE job application.
Attempt every safe step for this one row, then exit. Do not process another
application.

Company: {company}
Role: {role}
URL: {jobLink}
Resume PDF: {resumePdf}
Posting key: {postingKey}
Source: {source}
State item key: {key}
Notes carried from tracker: {notes}

Use Liam's Chrome profile for applications: profile name `Liam`, account
`liamvanpj@gmail.com`, profile directory `Default`. Ben (`bendov1010@gmail.com`,
`Profile 1`) is only for LinkedIn sourcing. Before opening the application URL,
make sure Chrome is on Liam's profile; if needed run
`open -na "Google Chrome" --args --profile-directory="Default"`. Use the
installed Codex Chrome plugin first for live ATS/application browser work so
cookies, saved logins, existing tabs, uploads, and portal state are preserved.
Use Codex Computer Use only as fallback if the Chrome plugin cannot communicate
with Chrome or cannot operate the current page. Dropdowns/typeaheads: open menu
→ click option → verify chip rendered. Never just type and move on.

Email 2FA / verification codes / magic links to liamvanpj@gmail.com are NOT
blockers. Use gmail@openai-curated MCP to read the code or click the link in
Chrome (already signed in), then continue. Only escalate if the email never
arrives, expires, or the verification switches to SMS / authenticator-app 2FA.

Confidence decision after final review:
- HIGH (every required field covered, no blocker): click submit, retrieve any
  emailed verification code via Gmail MCP, capture confirmation,
  run update_application_status.py, set state="submitted". Routine
  acknowledgements such as privacy/data-processing, equal-opportunity, recruiting
  contact consent, background-check disclosure notices, at-will employment
  notices, electronic communication notices, and truthful application-accuracy
  certifications count as covered and should not downgrade confidence.
- FRQ REVIEW OK: If an FRQ/custom written answer is drafted but should get Liam
  review, do not submit. Leave the tab open at the cleanest pre-submit point,
  set state="manual" with blocker/result containing the exact FRQ question, the
  drafted answer, and `awaiting Liam approval`. In the report, say why it was
  not submitted and include the FRQ draft. If Liam approves that FRQ answer in
  chat later, a follow-up worker may return to the open tab, submit the prepared
  application, capture confirmation, update tracker/cache, close the tab, and
  set state="submitted".
- MEDIUM (one uncertain or unsupported field): fill all safe fields, generate
  best-effort grounded answers from profile/resume evidence, leave tab open, set
  state="manual" with blocker like "Review needed: <question>".
- HARD blocker after attempt (account creation, fresh login when
  unauthenticated, SMS/authenticator-app 2FA, interactive CAPTCHA, Workday
  account/profile gate, non-routine legal signature/contract terms): leave the
  tab open at the blocker and set state="manual" with exact blocker. Do not skip
  a queued row merely because it is Workday/manual; attempt as far as safely
  possible first.
- Posting closed/404/redirected: set state="archived".

Update /tmp/fa_script_run_state.json item with key "{key}":
  state, result, blocker (if manual), confirmationEvidence (if submitted), updatedAt.

If submitted and confirmation evidence is captured, close that application tab.
If not submitted, leave the most useful partially completed application tab open
at the exact review/blocker point for Liam.

Exit when done.
```

## Run State File

`/tmp/fa_script_run_state.json` (separate namespace from the legacy skill's `/tmp/fa_run_state.json`). Schema mirrors the legacy file but `items[i].state` transitions are the only thing the orchestrator reads back.

## Liam's Standing Answers

Detailed in `OPERATING_CARD.md` rule 5. The condensed list is in the per-row prompt only as a reference — the agent re-reads the operating card on every run.

## Factual Resume Context

Every spawned agent must use Liam's real work history as the factual basis for
FRQs, values answers, achievement examples, and project examples. The row's
tailored `resume.tex` next to `resumePdf` is the
immediate source of truth. If `generic-resume/README.md` or
`generic-resume/resume.tex` exists, the agent must read those too and treat them
as the broader evidence bank. Never invent employers, internships, tools,
projects, metrics, dates, credentials, or responsibilities. If a requested
answer cannot be grounded in the resume/profile/tracker evidence, the agent
should use a supported adjacent example or leave the tab open for review.
Education dates are strict: University of Georgia BS Computer Science, started
Aug 2021, graduated Dec 2024. Never enter a graduation year before 2024, and
never answer that Liam graduated before 2020. If a form asks whether Liam
graduated before 2020, answer No.

## Cover Letters

Do not generate, render, write, paste, or upload cover letters. If a
cover-letter field is optional, leave it blank. If a cover-letter field is
required and cannot be skipped, leave the tab open and mark the row manual with
`Cover letter required; skipped by no-cover-letter policy`.

## Workday

Workday rows are queued for a best-effort attempt like every other row. The
worker should open the flow, use Liam's profile/autofill where available, and
fill safe fields if reachable. If Workday requires account creation/login,
unavailable profile data, legal steps, or other non-routine choices, leave the
tab open and record the precise blocker. To pre-mark Workday rows in the tracker
for Liam visibility:

```bash
python3 skills/finish-app-script/scripts/build_queue.py --mark-workday-manual
```

## Circuit Breaker

`run_queue.py` pauses the inner loop if 3 consecutive rows return
`state=manual`. This catches local bad streaks, Chrome plugin communication
loss, Chrome auth loss, network problems, or systemic blocker patterns before
burning more spawns in the same child process. `run_monitored_batches.py` should
then relaunch the inner runner when queued rows remain, unless the latest run
produced a fresh systemic Chrome plugin / browser blocker.

## Final Response

Orchestrator prints a summary: confirmed submissions, manual rows with blockers, archived rows, commits made. Tracker and visualizer cache reflect all confirmed submissions.
