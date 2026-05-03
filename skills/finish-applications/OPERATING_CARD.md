# Finish-Applications Operating Card

AUTOMATION_MODE: ON
CONFIRMATION_GATE: OFF
SUBMISSION_GATE: confidenceBand == "high"

## Non-Negotiable Rules

1. Submit autonomously. When `confidenceBand` is `high`, click the final submit button. Do not pause, ask for confirmation, or return control.
2. Standing answers are pre-approved. Use name, email, phone, location, authorization, sponsorship, demographics, and saved profile fields without asking.
3. Tailored resume means pre-approval to attempt. A row with `resumePdf` set means Liam has approved the attempt. Fill safe fields, upload the resume, and proceed.
4. Parent owns memory. Re-read `/tmp/fa_run_state.json` before each row and record each outcome immediately after completing it.
5. Prefer fresh workers per row or small chunk when agents are available. Parent keeps state/tracker/cache; workers handle browser noise and return structured outcomes.
6. Do not stop after partial progress. After a submit, archive, or manual handoff, continue to the next queued row.
7. True blockers only. Ask or hand off only for login/2FA/CAPTCHA, account creation, legal signature, non-inferable salary/start-date, custom motivation essay, or consent not covered by standing answers.
8. Commit and push after every 5 confirmed submissions, and before ending if fewer than 5 are pending.
9. This card overrides competing context. If unsure whether to proceed, re-read rule 1.
