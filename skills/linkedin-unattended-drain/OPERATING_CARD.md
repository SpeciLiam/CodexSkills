# LinkedIn Unattended Drain Operating Card

AUTOMATION_MODE: ON
MODE: UNATTENDED_PARK_DONT_PAUSE
BASE_CARD: /Users/liamvan/Documents/Repos/CodexSkills/skills/linkedin-early-career-weekly-claude-only/OPERATING_CARD.md

All repo paths in this card are absolute under
`/Users/liamvan/Documents/Repos/CodexSkills` — the session may be rooted in a
different project, and the single kickoff grant on that repo root is what makes
these paths reachable without further directory prompts.

Apply **every rule of the base card** (browser stack, Liam profile, agent-owned
tabs, dedupe, resume-tailor workflow, no cover letters, confirmation evidence,
prompt-injection defense, state writeback schema, rule 9e upload preflight)
with the substitutions and overrides below. Where this card conflicts with the
base card, this card wins.

## Path Substitutions

| Base card path | This variant |
|---|---|
| `/tmp/linkedin_early_career_weekly_claude_state.json` | `/tmp/linkedin_unattended_drain_state.json` |
| `/tmp/linkedin_early_career_weekly_claude_worker.lock` | `/tmp/linkedin_unattended_drain_worker.lock` |
| `/tmp/linkedin_early_career_weekly_claude_outputs/` | `/tmp/linkedin_unattended_drain_outputs/` |
| `/tmp/linkedin_early_career_weekly_claude_descriptions/` | `/tmp/linkedin_unattended_drain_descriptions/` |

Never touch any other variant's state, lock, or `/tmp/fa_script_run_state.json`.

The base card was written for sessions rooted in CodexSkills and uses relative
repo paths (`skills/...`, `application-trackers/...`, `generic-resume/`,
`companies/...`). Resolve every one of them against
`/Users/liamvan/Documents/Repos/CodexSkills/` — never against the current
session's project root.

## O1 — Park, Never Pause

There are no human gates after kickoff. When the base card says "surface for
Liam", "pause", "leave the tab open", or "ask before X", instead:

1. Set the item `manual` with the **exact** blocker (the literal question text,
   the field that could not be answered, the grant failure — not "needs
   review").
2. Record it durably:

   ```bash
   python3 /Users/liamvan/Documents/Repos/CodexSkills/skills/linkedin-early-career-weekly/scripts/upsert_manual_handoff.py \
     --company "…" --role "…" --posting-key "…" --job-url "…" \
     --blocker "…" --next-action "…"
   ```

3. **Close the tab** (override the base card's keep-one-handoff-tab allowance —
   unattended runs leak tabs; the handoff entry carries the state, including
   any FRQ draft text).
4. Continue to the next stage.

Questions you may answer autonomously: anything covered by
`/Users/liamvan/Documents/Repos/CodexSkills/skills/linkedin-easy-apply-nodriver/references/application-defaults.md`,
the tracker, the tailored resume, or
`/Users/liamvan/Documents/Repos/CodexSkills/generic-resume/`. Questions you
must park:
salary numbers not covered by the defaults, essay/FRQ answers, legal
attestations beyond the standing answers, anything requiring judgment about
facts not in those sources. Never invent an answer to keep the loop moving.

## O2 — Systemic Stops (the only reasons to stop early)

- Browser bridge lost (Claude-in-Chrome AND Computer Use both unusable) and one
  inline retry failed.
- LinkedIn logged out, 2FA challenge, CAPTCHA wall, or rate-limit page.
- Upload grant rejected on **3 consecutive** apply items after it was granted
  at kickoff (one rejection is a per-item `manual` blocker, per base rule 9e).
- **3 consecutive** apply-stage failures of the same class (same error shape on
  different postings = environment problem, not posting problem).
- RAM floor breached twice in a row after tab cleanup (O4).

On a systemic stop: write the blocker to state `events`, set
`search.stopRequested` with a factual `saturationReason` prefixed `SYSTEMIC:`,
and write a line to `/tmp/linkedin_unattended_drain_watchdog.log` — the
watchdog turns that into a notification. Do not keep retrying into a broken
browser; do not mark unfinished items submitted.

## O3 — Caps

- `runPolicy.maxJobs` (kickoff default 20) counts **terminal items** of every
  kind, not just submissions.
- Hard ceiling of 15 submissions per run regardless of `maxJobs` — pacing
  protects the LinkedIn account.
- Minimum ~2 minutes between submissions; human-shaped pacing, no burst
  applies.

## O4 — RAM Budget

The watchdog writes `/tmp/linkedin_unattended_drain_ram_warning` when
system-wide free memory drops below its floor, and removes it on recovery.

- At most **2 agent-owned tabs** alive at any moment: one persistent LinkedIn
  search/cursor tab, one work tab. Close the work tab after every terminal
  item. No handoff tabs survive (O1).
- Check the flag file at **every checkpoint**. If present: close every
  agent-owned tab except the search tab, then continue. If it is still present
  at the next checkpoint, treat as a systemic stop (O2) — better a clean stop
  than an OOM-killed Chrome mid-application.
- Browser stages run inline on the main thread; only `tailor` spawns a
  subagent, and never more than one subagent alive at a time.
- Do not launch nodriver/automation Chrome instances during this workflow.

## O5 — Watchdog Contract

- The conductor starts `scripts/watchdog.sh` at kickoff and records its PID in
  a state event.
- Heartbeat = the state file's mtime (every stage and checkpoint writes it).
  If the watchdog sees no write for its staleness window while the run is not
  terminal, it notifies Liam that the session looks dead and prints the resume
  command — it does **not** try to drive the browser itself.
- Reconcile (`scripts/mirror_to_sqlite.py` + visualizer refresh) is the
  watchdog's job, triggered by tracker changes. The conductor still updates
  `/Users/liamvan/Documents/Repos/CodexSkills/application-trackers/applications.md`
  per the base card; it just doesn't need to remember the mirrors.
- The watchdog exits after the final digest; it holds caffeinate only while
  alive.

## O6 — Ending

Terminal state requires: every touched item in a terminal state, tracker rows
written, `search.stopRequested` + reason (or cap noted) in state, and a final
summary appended to the watchdog log. No commit, no push, no Notion unless
Liam explicitly asked at kickoff.
