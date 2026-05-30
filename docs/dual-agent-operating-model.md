# Codex + Claude Operating Model

Use two agents as a reviewer/executor pair, not as simultaneous editors.

## Recommended Default

- Codex executes: repo inspection, edits, tests, browser QA, automation wiring, and final summaries.
- Claude thinks long: product framing, UI/design critique, architecture alternatives, copy, risk reviews, and recruiting workflow strategy.
- Claude Code can execute when a task is already isolated and the user starts there, but Codex should still perform final local verification when possible.

## Best Loop

1. Claude turns messy intent into a brief with goals, constraints, acceptance criteria, and risks.
2. Codex implements the smallest complete version and verifies it.
3. Claude reviews the diff or screenshots for design, missing states, hidden assumptions, and maintainability issues.
4. Codex applies selected fixes and reruns checks.

## When To Use Claude Subagents

- Use `design-critic` before or after visual/frontend work.
- Use `architecture-critic` before large refactors or multi-service changes.
- Use `recruiting-ops-reviewer` before high-volume application, outreach, or tracker automation.
- Use `safety-gate` before sends, submits, public comments, pushes, or destructive operations.
- Use `handoff-router` when there are multiple open handoff files and the next step is unclear.

## Guardrails

- One editing owner at a time.
- Handoff files must include touched files and out-of-scope files.
- The reviewing agent should be adversarial but concrete.
- The executing agent chooses which findings to apply and verifies after patching.
- External actions stay human-confirmed: applications, email, LinkedIn, Notion sync, GitHub PR comments, and paid purchases.
