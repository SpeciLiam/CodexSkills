---
name: recruiting-pipeline
description: Orchestrate Liam Van's full recruiting workflow across resume tailoring, application tracking, Gmail status refreshes, LinkedIn recruiter and engineer outreach, company prospecting, Apollo email lookup, and the Vercel visualizer, with optional routing to the separate Notion mirror skill only when requested.
---

# Recruiting Pipeline

Use this skill when the user wants the best end-to-end recruiting workflow, a daily recruiting plan, or help deciding which recruiting skill to run next.

This is the coordinator skill. It does not replace the specialized skills; it sequences them.

## Sources Of Truth

Use these in order:

1. Markdown tracker: `application-trackers/applications.md`
2. Outreach prospect tracker: `application-trackers/outreach-prospects.md`
3. Generated cache: `application-visualizer/src/data/tracker-data.json`

Markdown stays authoritative. The generated cache is the fast read model for dashboards and target builders.
Notion is a separate optional mirror handled by `notion-application-sync`; do not include it in normal recruiting runs.

## Daily Command

Start every recruiting session with:

```bash
python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py
```

Useful options:

```bash
python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py --format json
python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py --limit 8
python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py --mode linkedin
```

That script reads the generated tracker cache and emits a prioritized plan:

- Gmail/status refresh
- applications that are tailored but not applied
- recruiter outreach lane
- engineer outreach lane
- prospecting/Apollo gaps
- interview or assessment prep
- visualizer refresh/deploy commands

## Focused Modes

Use a focused mode when the user wants to run one lane without losing the adjacent work that keeps the tracker reliable:

```bash
python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py --mode resume
python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py --mode linkedin
python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py --mode recruiter
python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py --mode engineer
python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py --mode prospecting
python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py --mode prep
python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py --mode status
python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py --mode dashboard
python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py --mode notion
```

Mode behavior:

- `resume`: refresh status, tailor/update roles, apply ready rows, then queue recruiter and engineer outreach.
- `apply`: refresh status, submit ready tailored rows, then queue both LinkedIn lanes.
- `linkedin`: refresh status, run recruiter and engineer outreach, check prospecting gaps, then refresh the dashboard.
- `recruiter`: run the recruiter lane with prospecting and dashboard follow-through.
- `engineer`: run the engineer lane with prospecting and dashboard follow-through.
- `prospecting`: find company-level people/email gaps and surface related LinkedIn lanes.
- `prep`: focus on interviews and online assessments.
- `status`: focus on Gmail/application status changes.
- `dashboard`: only rebuild visualizer data/site output.
- `notion`: refresh website data and preview the optional Notion mirror.

When the user explicitly says "only LinkedIn outreach" or "just resume tailor," run the matching mode first, then perform only the companion steps that are listed for that mode.

If the cache is stale, run:

```bash
python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py
```

## Optimal Flow

Follow this sequence unless the user asks for a specific step:

1. **Refresh state**
   - Run the daily plan script.
   - Run `gmail-application-refresh` when statuses may have changed.
   - Refresh visualizer data after tracker edits.

2. **Add or tailor new roles**
   - Use `resume-tailor` for new job links.
   - Render and verify the one-page PDF.
   - Update `application-trackers/applications.md`.
   - Let fit score and `Reach Out` be set by the tracker helper unless the user overrides.

3. **Submit applications**
   - Prioritize high-fit `Resume Tailored` rows that are not applied.
   - After applying, use `gmail-application-refresh` or the status helper to mark `Applied`.

4. **Do LinkedIn outreach**
   - Use `linkedin-outreach`.
   - Treat recruiter and engineer as separate lanes.
   - For each `Reach Out` row, try to complete both:
     - one recruiter contact
     - one engineer contact
   - Recording recruiter outreach must not mark engineer outreach complete, and vice versa.
   - When speed matters, run recruiter and engineer outreach as two parallel Codex workstreams from the same refreshed cache snapshot.

5. **Build deeper prospect lists**
   - Use `company-prospecting` for companies that need more than LinkedIn invites.
   - Each company should have at least one recruiter and one engineer prospect when possible.
   - Export Apollo queue only after real names are selected.

6. **Monitor responses**
   - Use `gmail-application-refresh` to detect confirmations, rejections, assessments, and interviews.
   - High-confidence changes update markdown. Notion sync is separate and optional.
   - Ambiguous messages should be reported, not guessed.

7. **Prepare interviews and assessments**
   - Prioritize `Interviewing` and `Online Assessment` rows from the daily plan.
   - Keep factual notes in the tracker after each scheduling or prep event.

8. **Refresh dashboard**
   - Run the visualizer refresh.
   - Build the site before deploy:

```bash
cd application-visualizer && npm run build
```

## Skill Routing

- User asks for a whole recruiting session: run `--mode all`.
- User asks for only one recruiting lane: run the closest focused mode first.
- New job link or pasted posting: use `resume-tailor`.
- Need next LinkedIn people: use `linkedin-outreach`.
- Need company-level people plus emails: use `company-prospecting`.
- Need email/status updates: use `gmail-application-refresh`.
- Need dashboard data rebuilt: use `application-visualizer-refresh`.
- Need Notion mirroring or 12-hour schedule setup: use `notion-application-sync`.
- Need overall priorities: use this skill first.

## Parallel Workstreams

Use parallel Codex workstreams only when the lanes are independent and both can update through deterministic scripts.

Best parallel pattern:

1. Refresh the cache once:

```bash
python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py
```

2. Build separate lane queues from that same snapshot:

```bash
python3 skills/linkedin-outreach/scripts/build_outreach_targets.py --contact-type recruiter --limit 20 --format json
python3 skills/linkedin-outreach/scripts/build_outreach_targets.py --contact-type engineer --limit 20 --format json
```

3. Run two Codex workstreams:
   - Workstream A owns recruiter outreach only.
   - Workstream B owns engineer outreach only.

4. Each workstream records sends only through:

```bash
python3 skills/linkedin-outreach/scripts/update_outreach_tracker.py --contact-type recruiter ...
python3 skills/linkedin-outreach/scripts/update_outreach_tracker.py --contact-type engineer ...
```

5. After both finish, refresh the visualizer cache and rebuild the website.

Avoid more than two concurrent outreach workstreams unless each has a disjoint company list. Do not let parallel workers manually edit the same tracker row; they should use the lane-aware update script so recruiter and engineer fields merge cleanly.

## Guardrails

- Do not let a generated cache overwrite markdown truth.
- Do not invent contacts, emails, application statuses, or recruiter names.
- Keep recruiter and engineer outreach separate.
- Do not create Apollo emails from guessed patterns.
- Prefer small factual tracker notes over long summaries.
- If a row is ambiguous, leave it unchanged and report why.
