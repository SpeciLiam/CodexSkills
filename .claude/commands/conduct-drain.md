---
description: Claude-conducted, Codex-executed application drain with a reasoning checkpoint between every batch.
argument-hint: [overnight|auto] [batch-size, default 5]
---

# Conduct-Drain

Run the `conduct-drain` skill (`skills/conduct-drain/SKILL.md`). You (Claude) are
the conductor; Codex workers execute one application each.

**Mode:** default is **attended** — pause for FRQ approval and gate the push
behind `safety-gate` + the user. If `$ARGUMENTS` contains `overnight`, `auto`, or
`unattended` (or the user said "run while I sleep" / "just do everything"), use
**Unattended / Overnight Mode** from the skill: start `caffeinate -dimsu`, drop
`--no-push` so each batch auto-pushes, never pause for approval, and stop only on
systemic browser failure.

Loop:

1. **Plan** — refresh cache, `build_queue.py`, then audit
   `/tmp/fa_script_run_state.json` (dedupe, missing resume PDFs, mis-queued rows).
2. **Execute one batch** — `python3 skills/finish-app-script/scripts/run_queue.py --max-rows ${ARGUMENTS:-5} --no-push`. Do **not** use `run_monitored_batches.py`.
3. **Checkpoint** — re-read the state file and judge: systemic browser failure
   (stop, don't relaunch), tracker integrity (submitted rows must have
   confirmation evidence), FRQ/manual review queue, wrong-resume drift. Decide
   continue / pause / abort.
4. **Gate the push** — run the `safety-gate` subagent and confirm with Liam
   before `git push`.
5. **Reconcile** — refresh the visualizer cache and give a final summary.

Keep your own context bounded: read only the compact run-state file and outcome
tails between batches, not raw worker transcripts.
