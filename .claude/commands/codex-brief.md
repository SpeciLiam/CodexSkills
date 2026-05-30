---
description: Create a copy-pasteable prompt for Codex from Claude's current plan or review.
argument-hint: task or scope
---

# Codex Brief

Prepare a concise prompt for Codex based on this task: $ARGUMENTS

Include:

- goal
- repo/context summary
- files likely in scope
- exact requested action
- constraints and out-of-scope items
- verification expected
- any handoff file that should be read or updated

Make the prompt suitable for Codex as the local executor. Do not ask Codex to make broad unrelated refactors.
