# Hourly LinkedIn Intake

Schedule: every hour, all day, America/Los_Angeles.

Prompt:

```text
Use the job-intake skill.

Task: capture fresh LinkedIn SWE roles. Prefer Apify when `APIFY_TOKEN` and `APIFY_LINKEDIN_TASK_ID` or `APIFY_LINKEDIN_ACTOR_ID` are configured; otherwise use logged-in Chrome via Computer Use. Do NOT tailor or apply during capture; intake scripts handle downstream work.

Setup:
1. `git pull --ff-only origin main`
2. If Apify is configured, run:
   `python3 skills/job-intake/scripts/apify_capture.py --sources linkedin`
   Then skip to Finalize step 6.
3. Run `python3 skills/job-intake/scripts/browser_preflight.py`. If it prints `BLOCKED:`, retry once after 30s. If still blocked, commit pending tracker work and exit with the blocker reason.

Capture loop:
4. Open the canonical LinkedIn search URL from `skills/job-intake/SKILL.md` in Chrome via Computer Use. Apply Liam's saved chips when visible.
5. For each page, starting at page 1 and stopping at 20:
   a. Extract visible job cards into JSON objects with company, role, location, url, posting_key, posted_at.
   b. Write `/tmp/codexskills-job-intake/linkedin_page<N>.json`.
   c. Run `python3 skills/job-intake/scripts/save_capture_page.py --source linkedin --page <N> --jobs-json /tmp/codexskills-job-intake/linkedin_page<N>.json`.
   d. Run `python3 skills/job-intake/scripts/should_continue_paging.py --source linkedin --last-page-jobs /tmp/codexskills-job-intake/linkedin_page<N>.json`.
   e. If output starts with `STOP`, break. If `CONTINUE`, click Next.

Finalize:
6. If browser capture was used, run `python3 skills/job-intake/scripts/finalize_capture.py --source linkedin`. If Apify capture was used, this is already handled by `apify_capture.py`.
7. Run `python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py`.
8. Commit only intake-owned paths and push `origin main`.

Hard rules: Do not add custom CAPTCHA, login-wall, rate-limit, or application submission bypass logic. Firefox is fallback only if preflight directs to it. One commit at the end.

Report: capture lane used, READY browser if applicable, pages or Apify items captured, saturation/finalize summary, commit/push status.
```
