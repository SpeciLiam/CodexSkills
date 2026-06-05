---
description: Claude-conducted, Codex-executed LinkedIn early-career weekly drain with a reasoning checkpoint after every discover/tailor/apply stage.
argument-hint: [overnight|auto] [search-url] [freshness-seconds]
---

# LinkedIn Early-Career Weekly — Claude-Conducted (Codex workers)

Run the `linkedin-early-career-weekly-claude` skill
(`skills/linkedin-early-career-weekly-claude/SKILL.md`). You (Claude, Opus 4.8)
are the parent/conductor; fresh **Codex** workers execute exactly one stage each
(discover, tailor, or apply) and then exit. You never touch Chrome while a worker
is alive.

**Mode:** default is **attended** — surface blocking form questions / FRQ drafts
for approval and gate any push behind `safety-gate` + the user. If `$ARGUMENTS`
contains `overnight`, `auto`, or `unattended` (or the user said "run while I
sleep"), use the skill's unattended mode: start `caffeinate -dimsu`, auto-push,
never pause for approval, and stop only on systemic browser failure.

Loop:

1. **Plan** — refresh the cache, then
   `python3 skills/linkedin-early-career-weekly/scripts/build_run_state.py --max-jobs 0 --freshness-seconds 604800`
   (pass `--search-url` from `$ARGUMENTS` when given; use `--resume` to continue
   an interrupted run). Read the tracker/intake dedupe landscape and confirm
   `/tmp/linkedin_early_career_weekly_state.json`. Open Chrome in Liam's profile.
2. **Execute one stage** —
   `python3 skills/linkedin-early-career-weekly/scripts/run_stages.py --max-stages 1`.
   **Exactly one Codex worker at a time** — never raise the stage count in a
   single call beyond 1, never launch a second `run_stages.py`, and do **not**
   use `run_monitored.py`. One fresh Codex worker does the next stage, writes its
   outcome, and exits.
3. **Checkpoint** — re-read the state file and judge the single changed item:
   systemic browser/auth/extension-bridge failure (stop, don't relaunch), dedupe
   correctness (no duplicate rows, no revisited URLs), tracker integrity
   (submitted items must carry confirmation evidence), wrong-resume/tailoring
   drift, manual/FRQ review queue. Decide continue / pause / abort.
4. **Gate the push** — run the `safety-gate` subagent and confirm with Liam
   before `git push` (attended mode).
5. **Reconcile** — when the search saturates or a stop condition hits, refresh the
   visualizer cache and give a final summary.

Keep your own context bounded: read only the compact run-state file and the new
item between workers, not raw worker transcripts. Workers follow
`skills/linkedin-early-career-weekly/OPERATING_CARD.md` unchanged.
