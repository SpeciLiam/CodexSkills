# Hourly Greenhouse Intake

Schedule: every hour, all day, America/Los_Angeles, offset 30 minutes from LinkedIn.

Prompt:

```text
Use the job-intake skill.

Task: capture fresh Greenhouse/MyGreenhouse SWE roles. Prefer Apify when `APIFY_TOKEN` and `APIFY_GREENHOUSE_TASK_ID` or `APIFY_GREENHOUSE_ACTOR_ID` are configured; otherwise use the same per-page save and saturation pattern as LinkedIn. Browser is preferred but not required because Greenhouse has public boards.

Setup:
1. `git pull --ff-only origin main`
2. If Apify is configured, run:
   `python3 skills/job-intake/scripts/apify_capture.py --sources greenhouse`
   Then skip to Finalize step 6.
3. Run `python3 skills/job-intake/scripts/browser_preflight.py`. Note the result; proceed even if blocked.

Capture loop:
4. Open MyGreenhouse if browser is READY; otherwise use public Greenhouse search.
5. For each page, starting at page 1 and stopping at 15:
   a. Extract jobs into JSON objects with company, role, location, url, posting_key, posted_at.
   b. Write `/tmp/codexskills-job-intake/greenhouse_page<N>.json`.
   c. Run `python3 skills/job-intake/scripts/save_capture_page.py --source greenhouse --page <N> --jobs-json /tmp/codexskills-job-intake/greenhouse_page<N>.json`.
   d. Run `python3 skills/job-intake/scripts/should_continue_paging.py --source greenhouse --last-page-jobs /tmp/codexskills-job-intake/greenhouse_page<N>.json`.
   e. If output starts with `STOP`, break. If `CONTINUE`, page forward.

Finalize:
6. If browser/public-board capture was used, run `python3 skills/job-intake/scripts/finalize_capture.py --source greenhouse`. If Apify capture was used, this is already handled by `apify_capture.py`.
7. Run `python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py`.
8. Commit only intake-owned paths and push `origin main`.

Hard rules: skip senior/staff/principal/manager/intern/sales/recruiter/support roles by title regex. Do not tailor or apply directly. One commit at the end.

Report: capture lane used, browser state if applicable, pages or Apify items captured, saturation/finalize summary, commit status.
```
