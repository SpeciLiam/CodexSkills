---
name: linkedin-early-career-weekly
description: Durable LinkedIn early-career weekly application drain that avoids the older LinkedIn all-apply flow, starts from last-week entry-level software-engineer results, dedupes, spawns fresh Codex workers for discovery, resume tailoring, and one application at a time, and resumes from /tmp state through context degradation.
---

# LinkedIn Early-Career Weekly

Use this skill when Liam wants the new persistent LinkedIn flow: early-career
software engineering roles from the last week, deduped against the tracker,
tailored with a fresh worker, then applied with a separate fresh worker.

This is intentionally not based on `linkedin-apply-all`.

## Default Invocation

When this workflow is run from chat and persistent goal tools are available,
create a pursuing goal **before** launching any monitor, stage runner, browser
actor, or sub-agent, and keep it active for the whole drain (including across
context compaction). In Codex, use goal mode with the shared completion
condition below:

```text
/goal Drain the LinkedIn early-career weekly per the shared Persistence Goal
```

Keep that goal active and close it only when the workflow reaches search
saturation, a systemic blocker, or an explicit user stop. Do not launch
additional workers merely to satisfy the goal; the one-worker rule still wins.

### Persistence Goal (shared with the `linkedin-early-career-weekly-claude` variant)

Both variants pursue **one identical persistence goal** so either agent knows to
keep going. Keep this completion-condition text byte-identical across both
skills:

> Every fresh last-week LinkedIn Entry-level software-engineer posting from the
> configured search is discovered, deduped against the tracker, and driven to a
> terminal state — submitted with confirmation evidence, recorded as a precise
> manual blocker, marked already-applied/duplicate, or archived with a reason —
> until search saturation (`search.stopRequested` with a `saturationReason`) or
> `runPolicy.maxJobs`, with the markdown tracker and visualizer cache
> reconciled. Submit high-confidence applications when the tailored resume is
> verified, all required answers are truthful/standing-answer covered, and no
> true blocker remains. Stop early only on a systemic browser/auth/rate-limit
> blocker or an explicit user stop. Honor the one-worker / one-browser-actor
> rule; never spawn extra workers just to satisfy the goal.

When Liam asks to run this workflow from chat, launch the monitor:

```bash
python3 skills/linkedin-early-career-weekly/scripts/run_monitored.py
```

Resume after interruption or context compaction with:

```bash
python3 skills/linkedin-early-career-weekly/scripts/run_monitored.py --resume
```

The default search is LinkedIn software engineer, United States, Entry level,
posted in the last week:

```text
https://www.linkedin.com/jobs/search/?keywords=software+engineer&geoId=103644278&location=United+States&f_TPR=r604800&f_E=2&origin=JOB_SEARCH_PAGE_SEARCH_BUTTON
```

## Useful Flags

- `--resume` preserves `/tmp/linkedin_early_career_weekly_state.json`.
- `--max-jobs N` stops after N durable posting outcomes; default `0` means keep
  going until search saturation or a systemic blocker.
- `--max-stages N` runs only N worker stages, useful for testing.
- `--model MODEL` overrides the worker model. Default comes from
  `CODEX_LATEST_MODEL` or `gpt-5.5`. Use `--model default` to omit `-m` and use
  Codex config.
- `--no-refresh` skips the initial visualizer cache refresh.
- `--dry-run` prints worker commands/prompts without launching browser work.

## Architecture

```text
run_monitored.py
  - refreshes visualizer cache unless --resume or --no-refresh
  - builds/resumes /tmp/linkedin_early_career_weekly_state.json
  - restarts run_stages.py while progress is possible

run_stages.py
  - takes /tmp/linkedin_early_career_weekly_worker.lock
  - refuses parallel worker/stage execution while that lock is active
  - authorizes only its single child stage worker while holding the lock
  - advances existing discovered items before discovering more
  - preflights spawned-worker Chrome extension access before browser stages
  - launches one fresh Codex worker for one stage

fresh Codex worker
  - discover: uses Liam Chrome profile to capture and dedupe one LinkedIn posting
  - tailor: reads resume-tailor instructions, renders/verifies resume, updates tracker
  - apply: uses Liam Chrome profile, Chrome plugin first, Computer Use fallback
  - never uses Playwright, Playwright CLI, Puppeteer, npx browser tooling, or public scraping fallbacks
```

## Operating Card

Before each stage, re-read:

```text
skills/linkedin-early-career-weekly/OPERATING_CARD.md
```

Application workers should also read:

```text
skills/finish-app-script/OPERATING_CARD.md
```

They borrow the live-form submission guardrails only. They must not invoke the
finish-app-script queue or write `/tmp/fa_script_run_state.json`.

Workers must also read the shared application-answer context used by the other
recruiting skills:

```text
skills/linkedin-easy-apply-nodriver/references/application-defaults.md
```

## Durability

State lives at:

```text
/tmp/linkedin_early_career_weekly_state.json
```

Worker outputs live at:

```text
/tmp/linkedin_early_career_weekly_outputs/
```

Manual application pickup notes live at:

```text
application-trackers/manual-application-handoffs.txt
```

Full job descriptions should be saved under:

```text
/tmp/linkedin_early_career_weekly_descriptions/
```

The state tracks visited/skipped LinkedIn job URLs, result index, scroll
checkpoint, duplicate streak, and item stages. A fresh parent can resume from
only the operating card plus the state file.

## Low-Memory Browser Policy

This workflow runs on Liam's 16 GB RAM laptop and must keep Chrome light by
default.

- Keep at most two workflow tabs open during normal operation: one LinkedIn
  search/checkpoint tab and one active job/application tab.
- Do not leave manual/review tabs open by default. Record the exact blocker,
  URL, resume path, filled-field summary, next action, and any FRQ drafts in
  `application-trackers/manual-application-handoffs.txt`, state, and the
  tracker, then close/finalize the application tab.
- Keep a manual handoff tab only when the live page contains unrecoverable state
  that cannot be reconstructed from the recorded URL and answers. Even then,
  keep at most one handoff tab for the whole workflow and close older workflow
  handoff tabs after recording their state.
- Before opening a new application tab, clean up stale workflow tabs from prior
  submitted, archived, duplicate, or manually recorded items.
- Avoid broad DOM snapshots or full-page screenshots on heavy ATS pages unless
  needed for a blocker. Prefer narrow locators, visible text, and small targeted
  DOM reads.

## Guardrails

- One workflow worker and one browser actor at a time.
- Do not run a second monitor or worker while
  `/tmp/linkedin_early_career_weekly_worker.lock` belongs to an active process.
- Use Liam's Chrome profile for both LinkedIn discovery and applications:
  profile `Liam`, account `liamvanpj@gmail.com`, directory `Default`.
- Use only the Codex Chrome plugin and Codex Computer Use for browser work. Do
  not use Playwright, Playwright CLI, Puppeteer, `npx playwright`, local browser
  wrapper scripts, or public scraping fallbacks.
- Keep browser work in agent-owned Chrome tabs/tab groups so Liam can use
  Chrome at the same time. Do not claim, navigate, reload, or reuse Liam's
  active/current tab unless resuming that exact row's prepared handoff tab.
  Preflight this before navigating: if an agent-owned tab in the Codex tab group
  cannot be created, stop as a systemic browser blocker instead of touching a
  posting or marking it manual. Keep the low-memory policy above: one search
  tab, one active work tab, no pile of handoff tabs.
  Spawned `codex exec` workers may not have `tool_search`; `run_stages.py`
  injects the absolute Chrome plugin `browser-client.mjs` path so they can use
  the Node REPL JavaScript tool directly.
  If a spawned `codex exec` worker cannot access `agent.browsers.get("extension")`
  even though the desktop parent session can, treat that as a child-session
  Chrome bridge limitation. Do not retry the full LinkedIn run; run browser
  stages only from a plugin-visible desktop thread until the child bridge is
  available.
- Dedupe before every side effect.
- Do not invent jobs, tracker rows, resumes, confirmations, or application
  outcomes.
- Do not update Notion unless Liam explicitly asks.
- Do not commit or push unless Liam explicitly asks.
- Do not use `skills/linkedin-apply-all` as the base or state source.
