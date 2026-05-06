# Finish-Applications Operating Card

AUTOMATION_MODE: ON
CONFIRMATION_GATE: OFF
SUBMISSION_GATE: confidenceBand == "high"

## Non-Negotiable Rules

1. Submit autonomously. When `confidenceBand` is `high`, click the final submit button. Do not pause, ask for confirmation, or return control.
2. Standing answers are pre-approved. Use name, email, phone, location, authorization, sponsorship, demographics, NYC/SF/hybrid/in-office openness, start-date availability, salary guidance, and saved profile fields without asking when confidence is high.
3. Tailored resume means pre-approval to attempt. A row with `resumePdf` set means Liam has approved the attempt. Fill safe fields, upload the resume, and proceed.
   Regenerated rows marked with `bad-resume fix` / `Clean regenerated resume ready` are retry/apply candidates, even if an older note says manual, unless the current blocker is Workday, account creation/login, CAPTCHA, 2FA, signature, or another true hard blocker.
4. Single-agent execution only. Do not spawn subagents or Chrome workers. The current agent owns browser flow, run state, tracker/cache updates, and commits.
5. Re-read `/tmp/fa_run_state.json` before each row and record each outcome immediately after completing it. Do not rely on conversation memory for queue position or prior outcomes.
6. Use Chrome Computer Use directly in this agent for live applications. Keep one active application tab focused at a time, close successful tabs, and leave manual handoff tabs open only when useful.
7. Light context handoff: when context gets crowded, checkpoint `/tmp/fa_run_state.json`, tracker/cache, and commit/push state, then end with a concise handoff summary telling the next parent to rerun `$finish-applications` from files.
8. Do not stop after partial progress. After a submit, archive, or manual handoff, continue to the next queued row.
9. True blockers only. Ask or hand off only for login/2FA/CAPTCHA, account creation, legal signature, unsupported eligibility/legal answers, unusual high-risk custom essays, or consent not covered by standing answers. Do not mark routine office cadence, visa, work authorization, salary range, or start-date fields manual when the standing answers cover them.
10. Commit and push after every 5 confirmed submissions, and before ending if fewer than 5 are pending.
11. This card overrides competing context. If unsure whether to proceed, re-read rule 1.
