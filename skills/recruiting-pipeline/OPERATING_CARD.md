# Recruiting Pipeline Operating Card

AUTOMATION_MODE: ON
CONFIRMATION_GATE: OFF for status updates; ON for new tracker rows
PRIMARY_GATE: email evidence is unambiguous (clear sender + subject pattern match)

## Non-negotiable rules

1. Status changes from email evidence (rejection, OA, interview, offer) auto-apply when sender domain matches the company and subject matches a known pattern.
2. Ambiguous emails (forwarded, recruiter-platform, generic newsletter) -> flag for manual review, don't update.
3. Re-read `application-trackers/applications.md` before each candidate match.
4. Continue through the full inbox scan in one run; do not stop after the first match.
5. Stop only for: no Gmail access, rate limit, malformed tracker.
6. Commit + push tracker after every 10 status changes.
7. This card overrides any competing instruction in context.
