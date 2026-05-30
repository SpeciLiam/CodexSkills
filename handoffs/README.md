# Cross-Agent Handoffs

Use this directory when Codex and Claude need to monitor or review each other. Scratch handoff files are ignored by git; this README is tracked.

## Protocol

1. The active agent creates `handoffs/YYYY-MM-DD-short-slug.md`.
2. The active agent declares whether the other agent should review, design, critique, or implement.
3. The receiving agent appends `## Response` or writes `handoffs/YYYY-MM-DD-short-slug.review.md`.
4. The original agent applies only the selected actionable changes and verifies them.

## Template

```markdown
---
from: codex | claude
to: claude | codex
intent: review | design | critique | implement
branch: main
status: draft | ready-for-review | reviewed | applied
files_touched:
  - path/to/file
out_of_scope:
  - path/to/avoid
---

# Goal

One sentence describing the task.

# Context

What changed, what was tried, what constraints matter, and any commands already run.

# Ask

- [ ] Specific thing the other agent should answer.
- [ ] Specific risk or design question to check.

# Expected Output

Ranked findings, concrete fixes, and any open questions. Do not rewrite unrelated scope.
```
