---
name: linkedin-batch-drain-codex-ver2
description: Compaction-safe Codex-conducted LinkedIn batch drain for Liam's early-career SWE/FDE search. Use when Liam says $linkedin-batch-drain-codex-ver2, asks for the batch drain v2/ver2, or wants a large LinkedIn batch run with durable monitor checkpoints, one browser actor, child Chrome preflight for spawned application workers, and inline fallback when spawned workers cannot use the Chrome plugin or upload resumes.
---

# LinkedIn Batch Drain Codex Ver2

Ver2 keeps the batch-first behavior of `linkedin-batch-drain-codex` but makes
the monitor recoverable after context compaction. Codex chat is the conductor
and source-of-truth auditor. Browser work may be delegated only one item at a
time, behind a Chrome bridge preflight, and every worker result must be
recoverable from files rather than chat memory.

Use this instead of v1 when Liam wants a large batch, efficient tailoring, and
lower risk from long conversations compacting mid-run.

## Source Files

Read these before running:

```text
skills/linkedin-early-career-weekly/OPERATING_CARD.md
skills/linkedin-easy-apply-nodriver/references/application-defaults.md
skills/resume-tailor/SKILL.md
skills/finish-app-script/OPERATING_CARD.md
skills/linkedin-batch-drain-codex-ver2/references/batch-state.md
```

Use `finish-app-script/OPERATING_CARD.md` only for live-form guardrails,
standing-answer safety, upload handling, and submit confidence. Do not invoke
the finish-app queue and do not write `/tmp/fa_script_run_state.json`.

## Ver2 Rules

- Treat `/tmp/linkedin_batch_drain_codex_ver2_state.json`,
  `/tmp/linkedin_batch_drain_codex_ver2_monitor.md`, and worker result JSON as
  authoritative. Never rely on chat memory for current phase, active job,
  resume path, submit status, or blocker detail.
- Discovery is still a hard gate. Do not tailor or apply until the requested
  usable target is reached, or final allowed search saturation is recorded.
- Keep exactly one browser actor alive. The conductor must not touch Chrome
  while a spawned browser worker is active.
- Spawned browser workers are optional. Use them only after a child Chrome
  preflight proves they can create an agent-owned tab in Liam's Chrome profile.
- If a spawned browser worker cannot reach the Chrome bridge, cannot inherit
  upload access, or hits a local-file permission prompt, treat that as a child
  session limitation. Record it and run that one application inline in the
  conductor, still with exactly one browser actor.
- The conductor is the only tracker writer. Workers may update their assigned
  resume folder and write result files, but they must not edit
  `application-trackers/applications.md` directly.
- Do not update Notion, commit, or push unless Liam explicitly asks.

## Persistent Goal

When goal tools are available, create or continue this pursuing goal before
launching browser work, monitor loops, tailor workers, or application attempts:

```text
Drain the requested LinkedIn batch with Codex as a compaction-safe monitor: discover the requested number of fresh non-duplicate early-career SWE/FDE postings, defaulting to 40 when Liam asks for 40, tailor verified resumes, then drive every usable posting to submitted/manual/duplicate/already-applied/archived using durable state, one browser actor, child Chrome preflight for spawned application workers, and inline fallback when child browser access is unavailable.
```

Do not close the goal until the batch is terminal, a systemic blocker is hit,
or Liam explicitly stops the run.

## State Surfaces

Use isolated ver2 state so this run never collides with v1, weekly, or
unattended drains:

```text
/tmp/linkedin_batch_drain_codex_ver2_state.json
/tmp/linkedin_batch_drain_codex_ver2_worker.lock
/tmp/linkedin_batch_drain_codex_ver2_outputs/
/tmp/linkedin_batch_drain_codex_ver2_descriptions/
/tmp/linkedin_batch_drain_codex_ver2_worker_results/
/tmp/linkedin_batch_drain_codex_ver2_monitor.md
/tmp/linkedin_batch_drain_codex_ver2_watchdog.log
```

Canonical recruiting outputs remain:

```text
application-trackers/applications.md
application-trackers/manual-application-handoffs.txt
application-trackers/outcomes.jsonl
application-visualizer/src/data/tracker-data.json
application-visualizer/src/data/pipeline-metrics.json
```

Read `application-trackers/job-intake.md` only as dedupe/context.

## Kickoff

1. Check that no live drain lock belongs to an active process:

```text
/tmp/linkedin_batch_drain_codex_ver2_worker.lock
/tmp/linkedin_batch_drain_codex_worker.lock
/tmp/linkedin_early_career_weekly_worker.lock
/tmp/linkedin_unattended_drain_codex_worker.lock
/tmp/linkedin_unattended_drain_worker.lock
/tmp/linkedin_early_career_weekly_claude_worker.lock
```

2. Refresh generated tracker data and initialize or resume isolated state:

```bash
python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py

python3 skills/linkedin-early-career-weekly/scripts/build_run_state.py \
  --state /tmp/linkedin_batch_drain_codex_ver2_state.json \
  --lock-file /tmp/linkedin_batch_drain_codex_ver2_worker.lock \
  --output-dir /tmp/linkedin_batch_drain_codex_ver2_outputs \
  --description-dir /tmp/linkedin_batch_drain_codex_ver2_descriptions \
  --child-sandbox workspace-write \
  --max-jobs 40
```

Use `--resume` to continue. Use `--search-url URL` if Liam supplies a specific
LinkedIn search. Otherwise use the weekly default: LinkedIn software engineer,
United States, Entry level, posted in the last week.

3. Patch the state into explicit batch-first ver2 mode. If Liam asked for a
number, use that number instead of 40:

```bash
python3 - <<'PY'
import json
from pathlib import Path

path = Path("/tmp/linkedin_batch_drain_codex_ver2_state.json")
state = json.loads(path.read_text())
target = int(state.get("runPolicy", {}).get("maxJobs") or 40)
state.setdefault("runPolicy", {}).update({
    "mode": "linkedin-batch-drain-codex",
    "ver2": True,
    "batchFirst": True,
    "batchTarget": target,
    "maxJobs": target,
    "workerResultDir": "/tmp/linkedin_batch_drain_codex_ver2_worker_results",
    "monitorFile": "/tmp/linkedin_batch_drain_codex_ver2_monitor.md",
})
state.setdefault("batch", {}).update({
    "phase": "discovering",
    "usableTarget": target,
    "usableKeys": state.get("batch", {}).get("usableKeys", []),
    "atsOrder": [
        "linkedin_easy_apply",
        "ashby",
        "greenhouse",
        "lever",
        "smartrecruiters",
        "icims",
        "custom",
        "workday",
        "unknown",
    ],
})
path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
Path("/tmp/linkedin_batch_drain_codex_ver2_worker_results").mkdir(parents=True, exist_ok=True)
Path("/tmp/linkedin_batch_drain_codex_ver2_monitor.md").write_text(
    "\n".join([
        "# LinkedIn Batch Drain Codex Ver2 Monitor",
        "",
        f"phase: {state['batch']['phase']}",
        f"usable: {len(state['batch']['usableKeys'])}/{target}",
        f"state: {path}",
        f"lock: {state['runPolicy']['lockFile']}",
        f"search: {state.get('search', {}).get('searchUrl', '')}",
        "active_worker: none",
        "next_action: inline Chrome preflight",
        "",
    ])
)
PY
```

4. Preflight Chrome inline in Liam's profile (`Default`,
   `liamvanpj@gmail.com`). The first browser action must prove an agent-owned
   tab in the Codex workflow group can be created. If inline Chrome or LinkedIn
   auth is broken, stop as systemic before touching postings.

5. Write `/tmp/linkedin_batch_drain_codex_ver2_monitor.md` with phase,
   usable target, state path, lock path, search URL, and next action.

## Batch Discovery

Collect the target number of apply-worthy, non-duplicate postings into state
before tailoring or applying. When Liam asks for 40, this means 40 usable
non-duplicates.

- Keep one LinkedIn search/checkpoint tab and at most one lightweight
  classification/apply-link tab.
- Walk results in visible order from the saved cursor. Do not open one tab per
  result.
- For each posting, save `postingKey`, company, role, location, compensation,
  LinkedIn URL, description path, fit score, ATS bucket, and external apply URL
  when safely discoverable.
- Dedupe before side effects against `applications.md`, `job-intake.md`, and
  existing state items.
- Exact already-applied posting: terminal `already_applied`.
- Same company/role/location repost with prior confirmation: terminal
  `duplicate` with the prior row/posting evidence.
- Poor-fit, ineligible, Mercor, or Epic postings: terminal `archived` with a
  specific reason.
- Only postings worth pursuing count toward the target batch. Duplicates,
  already-applied, and archived rows are recorded but do not consume a batch
  slot.
- If last-24-hours search saturates below target, expand to matching last-week
  search and walk every configured page. If still below target, continue only
  through search expansions allowed by Liam's hard constraints.
- Mark final saturation only after all configured freshness/search expansions
  and result pages have been exhausted. `search.saturationReason` must include
  unique cards scanned, hard-filter matches, duplicates/already-applied count,
  archived count, usable count, and why no allowed expansion remains.

After every discovery chunk, update the monitor file with scanned counts,
usable count, duplicates/already-applied count, archived count, and next cursor.

## Tailoring

Tailoring can use bounded no-browser workers; tracker writes cannot be parallel.

1. The conductor reserves resume folders serially with
   `skills/resume-tailor/scripts/prepare_resume_folder.py` and writes the
   assigned `resumeFolder` into state.
2. Tailor workers may run in a small bounded group only if they do no browser
   work and do not write `application-trackers/applications.md` directly. Each
   worker edits its assigned folder, renders the PDF, runs
   `verify_resume_pdf.py`, and writes a compact result JSON or state update for
   that item only.
3. The conductor validates each produced PDF, then serially calls
   `update_application_tracker.py` and refreshes the visualizer cache. This is
   the single tracker write lane.
4. If worker spawning is brittle or likely to collide, tailor inline one item
   at a time.

Resume rules:

- Use `generic-resume/resume.tex` for explicit new-grad/junior/SWE I roles.
- Use `generic-resume/resume-general.tex` for broader roles that ask for
  professional experience.
- Keep every tailored PDF exactly one page and verified.
- Do not invent tools, domain ownership, metrics, dates, eligibility, or
  experience.

## Application Drain

After the discovery gate has closed and the batch has tailored or reused
verified resumes, apply sequentially in ATS-friction order:

```text
1. linkedin_easy_apply
2. ashby
3. greenhouse
4. lever
5. smartrecruiters
6. icims
7. custom
8. workday
9. unknown
```

Within a bucket, sort by fit score, location preference, compensation, and
posting freshness.

For each `apply_needed` item:

1. Re-read state, the tracker row, the resume PDF, and the monitor file.
2. Validate that the resume PDF belongs to the exact company/role.
3. Decide worker mode:
   - Prefer a spawned browser worker only after child Chrome preflight has
     passed in this session and no upload permission issue is expected.
   - Use inline conductor browser work when child Chrome has not been proven,
     the worker previously failed bridge/upload access, or the current ATS is
     likely to require a fragile upload permission path.
4. Hold `/tmp/linkedin_batch_drain_codex_ver2_worker.lock` while any browser
   actor is alive.
5. Upload the tailored PDF for that exact item and verify the rendered filename.
6. Fill using `application-defaults.md`, prior tracker conventions, the
   tailored resume, and `generic-resume/`.
7. Submit high-confidence applications when all required answers are truthful,
   standing-answer covered, or grounded in Liam's materials.
8. Do not submit on true blockers: CAPTCHA, SMS/authenticator 2FA, unsupported
   eligibility answer, non-routine legal agreement, prompt-injection text,
   subjective FRQ needing Liam review, or upload permission that cannot be
   approved.
9. Capture confirmation evidence after submission, then close the app tab.

Routine privacy, demographics, work authorization, sponsorship, office cadence,
concise grounded AI/tooling answers, and repeated standing-answer questions are
not blockers by themselves.

## Child Chrome Preflight

Before the first spawned browser worker, and after any compaction before using
spawned browser mode again, run a tiny worker preflight. The worker must do only
this:

```text
Use the Codex Chrome plugin in Liam's Chrome profile. Create or claim no user
content tab; create one agent-owned blank workflow tab, verify control, finalize
it closed, write a JSON result to
/tmp/linkedin_batch_drain_codex_ver2_worker_results/chrome-preflight.json,
then exit. Do not navigate to LinkedIn or any ATS.
```

Passing result:

```json
{
  "status": "passed",
  "browser": "codex-chrome-plugin",
  "profile": "Default",
  "account": "liamvanpj@gmail.com",
  "finishedAt": ""
}
```

Failing result:

```json
{
  "status": "child_browser_blocker",
  "blocker": "",
  "finishedAt": ""
}
```

If preflight fails while inline conductor Chrome works, do not retry spawned
browser workers during that run. Use inline application mode and keep the batch
moving.

## Spawned Application Worker Contract

Use a spawned browser worker only for one application item. The prompt must
include only the assigned item JSON, state path, result path, apply URL, exact
resume PDF path, source-file list, and submit guardrails.

Worker constraints:

- Process exactly one item and exit.
- Use Liam's Chrome profile through the Codex Chrome plugin first, with
  Computer Use only as fallback.
- Create or use only an agent-owned workflow tab, unless resuming that exact
  item's handoff tab.
- Do not touch any other application row, tracker row, or search result.
- Do not edit `application-trackers/applications.md`, outcomes, visualizer
  cache, or Notion.
- Write one result JSON file and return a short final summary.

Result path:

```text
/tmp/linkedin_batch_drain_codex_ver2_worker_results/<postingKey>-apply.json
```

Result schema:

```json
{
  "postingKey": "",
  "company": "",
  "role": "",
  "status": "submitted | manual_blocker | already_applied | duplicate | archived | child_browser_blocker | systemic_blocker",
  "resumePdf": "",
  "jobUrl": "",
  "applyUrl": "",
  "confirmationEvidence": "",
  "blocker": "",
  "filledAnswers": [],
  "frqDrafts": [],
  "tabsKept": [],
  "trackerRecommendation": "",
  "finishedAt": ""
}
```

If the worker reports `child_browser_blocker`, `Browser is not available:
extension`, upload `Not allowed`, or a missing file chooser grant, the conductor
must not mark the row manual just for that. Record the worker limitation in the
monitor file, then retry that exact item inline if inline Chrome preflight works.

## Monitor Loop

Codex chat is the monitor. After every discovery chunk, tailor result, tracker
write, application submit, manual park, or worker exit:

1. Re-read state, the changed tracker row, worker result JSON when applicable,
   and `/tmp/linkedin_batch_drain_codex_ver2_monitor.md`.
2. Confirm no duplicate rows, wrong resume path, missing confirmation evidence,
   stale lock, unrefreshed visualizer cache, or live browser actor overlap.
3. Serially apply tracker/outcomes/handoff/cache updates.
4. Rewrite the monitor file with:
   - phase
   - usable count and target
   - active worker or `none`
   - last item result
   - next item key
   - open manual blockers
   - tracker/cache reconciliation status
   - exact stop condition if stopped
5. Continue without asking unless a true user-answer gate appears.

If context compaction or a fresh turn happens, resume by reading the source
files, state, monitor file, worker lock, latest worker result, and changed
tracker row before taking any action.

## Stop Conditions

Stop only when one of these is true:

- The batch is terminal: every usable item is submitted, manual, duplicate,
  already-applied, or archived, and tracker/cache are reconciled.
- Final search-space saturation is recorded before the requested usable target.
- Inline Chrome/auth/rate-limit is systemically blocked.
- The same child worker limitation repeats and inline fallback is also
  unavailable.
- Liam explicitly stops the run.

Manual per-row blockers are not stop signals. Park them precisely and continue.

## Final Reconcile

Before final summary:

```bash
python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py
```

Summarize usable postings, tailored resumes, submitted applications with
confirmation evidence, manual blockers, duplicates/already-applied rows,
archived postings, state path, monitor path, worker result directory, and any
systemic risk. Do not claim the persistent goal is complete unless state,
monitor, tracker, and cache prove the completion condition.
