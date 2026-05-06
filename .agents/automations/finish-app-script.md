# Finish App Script Queue

Schedule: on demand. Run during active application sessions or after job-intake / Gmail refresh.

Prompt:

```text
Use the finish-app-script skill.

Task: drain the tailored-resume application queue from chat/phone by rotating fresh Codex CLI parent processes through small live-browser batches. Each fresh parent owns Chrome/Computer Use directly for up to two rows, then exits so the next process starts with clean context.

Setup:
1. `git pull --ff-only origin main`
2. `python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py`
3. `python3 skills/finish-app-script/scripts/build_queue.py`

Run:
4. `python3 skills/finish-app-script/scripts/run_batches.py`

Optional flags on run_batches.py:
- `--batch-size N` — rows per fresh Codex CLI process, default 2
- `--max-batches N` — cap fresh processes (smoke test)
- `--model MODEL` — override default gpt-5.5
- `--timeout SECONDS` — per-batch timeout, default 1800
- `--child-sandbox MODE` — child process sandbox, default danger-full-access
- `--no-commit` / `--no-push` — disable auto-commit/push
- `--dry-run` — print prompts without invoking codex exec

Rules:
- Each fresh parent reads `skills/finish-app-script/OPERATING_CARD.md` first.
- High-confidence rows: submit autonomously, run `update_application_status.py`, set state="submitted", capture confirmation, close the submitted application tab.
- Medium-confidence rows (FRQ / one uncertain field): fill all safe fields, generate best-effort answer, leave the tab open at the cleanest review point, set state="manual" with exact blocker, continue the batch from a new tab if capacity remains.
- True blockers (login/2FA/CAPTCHA/Workday/account creation/legal signature): mark state="manual" with exact blocker, leave useful handoff tabs open, continue or exit according to the batch prompt.
- Orchestrator commits + pushes every 5 confirmed submissions.
- If Chrome/Computer Use itself is unavailable, stop early because that is a systemic runner blocker.

Hard rules: do not commit unrelated files. Tracker/cache only. Do not push from inside fresh parents — the outer orchestrator owns commits.

Report: confirmed submissions, manual rows with blockers, archived rows, commits made, current queue depth remaining.
```
