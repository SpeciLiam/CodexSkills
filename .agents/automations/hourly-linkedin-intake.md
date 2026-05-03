# Hourly LinkedIn Intake

Schedule: every hour, all day, America/Los_Angeles.

Prompt:

```text
Use the job-intake skill.

Task: capture fresh LinkedIn SWE roles using logged-in Chrome via Computer Use. Save per page. Stop on saturation. Do NOT tailor or apply; finalize_capture.py handles downstream intake work.

Setup:
1. `git pull --ff-only origin main`
2. Run `python3 skills/job-intake/scripts/browser_preflight.py`. If it prints `BLOCKED:`, retry once after 30s. If still blocked, commit pending tracker work and exit with the blocker reason.

Capture loop:
3. Open the canonical LinkedIn search URL from `skills/job-intake/SKILL.md` in Chrome via Computer Use. Apply Liam's saved chips when visible.
4. For each page, starting at page 1 and stopping at 20:
   a. Extract visible job cards into JSON objects with company, role, location, url, posting_key, posted_at.
   b. Write `/tmp/codexskills-job-intake/linkedin_page<N>.json`.
   c. Run `python3 skills/job-intake/scripts/save_capture_page.py --source linkedin --page <N> --jobs-json /tmp/codexskills-job-intake/linkedin_page<N>.json`.
   d. Run `python3 skills/job-intake/scripts/should_continue_paging.py --source linkedin --last-page-jobs /tmp/codexskills-job-intake/linkedin_page<N>.json`.
   e. If output starts with `STOP`, break. If `CONTINUE`, click Next.

Finalize:
5. Run `python3 skills/job-intake/scripts/finalize_capture.py --source linkedin`.
6. Run `python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py`.
7. Commit only intake-owned paths and push `origin main`.

Hard rules: Chrome via Computer Use only for LinkedIn. Firefox is fallback only if preflight directs to it. Do not bypass CAPTCHA, login walls, LinkedIn rate limits, or application submission boundaries. One commit at the end.

Report: READY browser, pages captured, saturation reason, finalize summary, commit/push status.
```
