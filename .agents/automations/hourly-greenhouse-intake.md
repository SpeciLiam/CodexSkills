# Hourly Greenhouse Intake

Schedule: every hour, all day, America/Los_Angeles, offset 30 minutes from LinkedIn.

Prompt:

```text
Use the job-intake skill.

Task: capture fresh Greenhouse/MyGreenhouse SWE roles. Use the same per-page save and saturation pattern as LinkedIn. Browser is preferred but not required because Greenhouse has public boards.

Setup:
1. `git pull --ff-only origin main`
2. Run `python3 skills/job-intake/scripts/browser_preflight.py`. Note the result; proceed even if blocked.

Capture loop:
3. Open MyGreenhouse if browser is READY; otherwise use public Greenhouse search.
4. For each page, starting at page 1 and stopping at 15:
   a. Extract jobs into JSON objects with company, role, location, url, posting_key, posted_at.
   b. Write `/tmp/codexskills-job-intake/greenhouse_page<N>.json`.
   c. Run `python3 skills/job-intake/scripts/save_capture_page.py --source greenhouse --page <N> --jobs-json /tmp/codexskills-job-intake/greenhouse_page<N>.json`.
   d. Run `python3 skills/job-intake/scripts/should_continue_paging.py --source greenhouse --last-page-jobs /tmp/codexskills-job-intake/greenhouse_page<N>.json`.
   e. If output starts with `STOP`, break. If `CONTINUE`, page forward.

Finalize:
5. Run `python3 skills/job-intake/scripts/finalize_capture.py --source greenhouse`.
6. Run `python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py`.
7. Commit only intake-owned paths and push `origin main`.

Hard rules: skip senior/staff/principal/manager/intern/sales/recruiter/support roles by title regex. Do not tailor or apply directly. One commit at the end.

Report: browser state, pages captured, saturation reason, finalize summary, commit status.
```
