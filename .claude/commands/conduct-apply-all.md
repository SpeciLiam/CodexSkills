---
description: Claude-conducted, Codex-executed LinkedIn apply-all drain with a reasoning checkpoint after every single application.
argument-hint: [overnight|auto] [search-url] [freshness 24h|week|month]
---

# Conduct-Apply-All

Run the `conduct-apply-all` skill (`skills/conduct-apply-all/SKILL.md`). You
(Claude, Opus 4.8) are the conductor/monitor; fresh Codex workers execute one
posting each — they tailor the resume for the posting first, then apply, then
exit. You never touch Chrome while a worker is alive.

**Mode:** default is **attended** — surface blocking form questions / FRQ drafts
for approval and gate the push behind `safety-gate` + the user. If `$ARGUMENTS`
contains `overnight`, `auto`, or `unattended` (or the user said "run while I
sleep" / "just do everything"), use **Unattended / Overnight Mode** from the
skill: start `caffeinate -dimsu`, auto-push, never pause for approval, and stop
only on systemic browser failure.

Loop:

1. **Plan** — refresh cache, then `build_run_state.py --worker codex --missing-resume-policy tailor`
   (pass `--search-url` / `--freshness` from `$ARGUMENTS` when given). Read the
   tracker/intake dedupe landscape and confirm `/tmp/linkedin_apply_all_state.json`.
   Open Chrome in Liam's profile.
2. **Execute one application** — `python3 skills/linkedin-apply-all/scripts/run_queue.py --worker codex --batch-size 1 --max-workers 1`.
   Do **not** use `run_monitored_queue.py`. One fresh Codex worker walks to the
   next substantive card, tailors, applies, writes the outcome, exits.
3. **Checkpoint** — re-read the state file and judge the single changed item:
   systemic browser/auth/rate-limit failure (stop, don't relaunch), dedupe
   correctness (no duplicate rows), tracker integrity (submitted items must carry
   confirmation evidence), wrong-resume/tailoring drift, manual/FRQ review queue.
   Decide continue / pause / abort.
4. **Gate the push** — run the `safety-gate` subagent and confirm with Liam
   before `git push` (attended mode).
5. **Reconcile** — when the search saturates or a stop condition hits, refresh the
   visualizer cache and give a final summary.

Keep your own context bounded: read only the compact run-state file and the new
item between workers, not raw worker transcripts.
