# Application Trackers

Use this directory for markdown trackers that summarize roles you have tailored resumes for.

Current tracker:

- `applications.md`: master tracker for tailored resumes and active job links
- `notion-config.md`: the configured Notion parent page and database for mirrored tracking
- `applications.md` should show `Total applications tracked: N` near the top, plus quick summary counts for applied, unapplied, rejected, archived, outreach targets, and high-fit roles

Recommended Notion tracker:

- A Notion database named `Application Tracker`
- Include the running total in the database title or primary table view name, such as `Applications (12)`, so the count is visible at a glance
- Primary table view sorted by `Date Added` descending
- A `Status` select property with clear stages such as `Resume Tailored`, `Applied`, `Online Assessment`, `Interviewing`, `Rejected`, and `Offer`
- `Referral` as a checkbox for fast scanning
- `Applied` as a checkbox so completed applications show a clear green check
- `Resume PDF` as a URL property
- `Job Link` as a URL property
- `Reach Out` as a checkbox for high-priority recruiter outreach targets
- `Fit Score` as a number property so you can sort or filter the strongest matches

Suggested Notion properties:

- `Company`: title
- `Role`: rich text
- `Posting Key`: rich text
- `Date Added`: date
- `Status`: select
- `Applied`: checkbox
- `Referral`: checkbox
- `Referral Name`: rich text
- `Location`: rich text
- `Source`: select
- `Job Link`: URL
- `Resume PDF`: URL
- `Notes`: rich text
- `Reach Out`: checkbox
- `Fit Score`: number

Current configured Notion tracker:

- Parent page: `https://www.notion.so/33ae4796acaf80a7b50dca069e050aca`
- Database: `https://www.notion.so/f305a0c7116d4c07b1ca053e0b4adbdd`

Automated Notion score sync:

- Export a Notion internal integration token as `NOTION_TOKEN`
- Share the Application Tracker database with that integration
- Recompute markdown scores and sync them into Notion with:
  `python3 skills/resume-tailor/scripts/score_application_tracker.py --sync-notion --update-notion-title`
- Or sync current markdown values to Notion without recomputing first:
  `python3 skills/resume-tailor/scripts/sync_notion_scores.py --update-title`
- New single-role tracker updates can also sync immediately with:
  `python3 skills/resume-tailor/scripts/update_application_tracker.py ... --sync-notion --update-notion-title`

Recommended fields:

- `Company`: target company
- `Role`: job title
- `Applied`: whether you have actually submitted the application yet
- `Status`: high-level stage such as `Resume Tailored`, `Applied`, `Online Assessment`, `Interviewing`, `Rejected`, or `Offer`
- `Company Resume`: click the company plus role label to open that tailored PDF directly
- `Referral`: `No`, `Requested`, `Yes`, or the referrer name
- `Fit Score`: 1 to 10 heuristic for overall fit and desirability
- `Reach Out`: `Yes` for roles worth proactive recruiter outreach based on fit, geography, and company quality
- `Date Added`: when the role was first tracked
- `Posting Key`: stable role-specific identifier derived from the job link so multiple roles at one company do not collide
- `Location`: city, state, remote, or hybrid note
- `Source`: Ashby, LinkedIn, company careers page, etc.
- `Job Link`: direct posting link
- `Resume Folder`: local folder for the tailored version
- `Resume PDF`: final file you would upload
- `Notes`: recruiter name, follow-up date, compensation, or interview notes

Recommended company folder layout for multiple roles:

- `companies/<Company>/<Role_Slug>/<Candidate_Name>_Resume`
- example: `companies/Microsoft/Software_Engineer_II/Liam_Van_Resume`
- if the same company and same role are tailored more than once, keep the role folder and suffix the resume folder as `_2`, `_3`, and so on

If you want the tracker to become more application-focused later, the most helpful extra inputs are:

- application date
- recruiter name
- follow-up date
- compensation range
- interview stage notes

Scoring preferences live in [scoring-profile.json](/Users/liamvan/Documents/Repos/CodexSkills/application-trackers/scoring-profile.json). The default profile biases toward New York roles, strong software engineering fit, worthwhile non-agency companies, and a `Reach Out` threshold of 8 out of 10.
