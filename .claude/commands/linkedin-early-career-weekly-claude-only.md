---
description: Claude-only LinkedIn early-career weekly drain — Claude conductor plus fresh Claude subagent workers, no Codex, reasoning checkpoint after every stage.
argument-hint: [overnight|auto] [search-url] [freshness-seconds]
---

# LinkedIn Early-Career Weekly — Claude-Only

Run the `linkedin-early-career-weekly-claude-only` skill
(`skills/linkedin-early-career-weekly-claude-only/SKILL.md`). You (Claude, Opus
4.8) are the conductor **and** every worker is a fresh Claude subagent (Agent
tool, `general-purpose`). **No Codex** — no `codex exec`, no `run_stages.py`, no
Codex Chrome plugin. Browser work uses Claude-in-Chrome first, Computer Use
fallback, in Liam's Chrome profile.

**Mode:** default is **attended** — surface blocking form questions / FRQ drafts
for approval and gate any push behind `safety-gate` + the user. If `$ARGUMENTS`
contains `overnight`, `auto`, or `unattended`, use the skill's unattended mode:
start `caffeinate -dimsu`, auto-push, never pause for approval, stop only on
systemic browser failure.

Loop:

1. **Plan** — refresh the cache, then build the **isolated** state with
   `python3 skills/linkedin-early-career-weekly/scripts/build_run_state.py --state /tmp/linkedin_early_career_weekly_claude_state.json --lock-file /tmp/linkedin_early_career_weekly_claude_worker.lock --output-dir /tmp/linkedin_early_career_weekly_claude_outputs --description-dir /tmp/linkedin_early_career_weekly_claude_descriptions --max-jobs 0 --freshness-seconds 604800`
   (pass `--search-url` from `$ARGUMENTS` when given; `--resume` to continue).
   Read the tracker/intake dedupe landscape. Open Chrome in Liam's profile.
2. **Select the next stage** from the isolated state: apply-ready items first,
   then tailor-ready, then discover.
3. **Execute one stage** — take the isolated worker lock, then launch **one**
   `general-purpose` Claude subagent with the matching stage prompt (it reads
   `skills/linkedin-early-career-weekly-claude-only/OPERATING_CARD.md`, does one
   stage with Claude-in-Chrome / Computer Use, writes the isolated state, returns
   a one-line summary, exits). **Exactly one worker at a time** — never two
   subagents, and never operate Chrome yourself while a worker is alive. If a
   subagent can't reach the browser bridge, run that one browser stage inline
   yourself (still one actor); `tailor` always works as a subagent.
4. **Checkpoint** — re-read the isolated state and judge the single changed item:
   systemic browser/auth failure (stop), dedupe correctness, tracker integrity
   (submitted items must carry confirmation evidence), wrong-resume/tailoring
   drift, manual/FRQ review queue. Decide continue / pause / abort.
5. **Gate the push** — `safety-gate` + Liam before `git push` (attended), then
   reconcile by refreshing the visualizer cache and give a final summary.

Keep your own context bounded: read only the compact isolated run-state file and
the new item between workers.
