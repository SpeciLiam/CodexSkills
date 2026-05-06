# Finish App Script Queue

Schedule: on demand. Run during active application sessions or after job-intake / Gmail refresh.

Prompt:

```text
Use the finish-app-script skill.

Task: drain the tailored-resume application queue by spawning one fresh `codex exec` per ready row, so each agent has a clean context with the submission rule embedded directly in its prompt.

Setup:
1. `git pull --ff-only origin main`
2. `python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py`
3. `python3 skills/finish-app-script/scripts/build_queue.py`

Run:
4. `python3 skills/finish-app-script/scripts/run_queue.py`

Optional flags on run_queue.py:
- `--max-rows N` — cap rows (smoke test)
- `--model MODEL` — override default gpt-5.5
- `--timeout SECONDS` — per-row timeout, default 360
- `--no-commit` / `--no-push` — disable auto-commit/push
- `--dry-run` — print prompts without invoking codex exec

Rules:
- Each spawned agent reads `skills/finish-app-script/OPERATING_CARD.md` first.
- High-confidence rows: agent submits autonomously, runs `update_application_status.py`, sets state="submitted".
- Medium-confidence rows (FRQ / one uncertain field): agent fills all safe fields, generates best-effort answer, leaves the tab open, sets state="manual" with exact blocker. Never stalls the queue.
- True blockers (login/2FA/CAPTCHA/Workday/account creation/legal signature): agent marks state="manual" with exact blocker, exits.
- Orchestrator commits + pushes every 5 confirmed submissions.
- Circuit breaker: 3 consecutive manual outcomes → stop the run (signals Chrome auth loss / network issue).

Hard rules: do not commit unrelated files. Tracker/cache only. Do not push from inside spawned agents — the orchestrator owns commits.

Report: confirmed submissions, manual rows with blockers, archived rows, commits made, current queue depth remaining.
```
