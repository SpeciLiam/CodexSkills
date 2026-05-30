---
name: dual-agent-orchestration
description: Coordinate Codex and Claude Code as an executor/reviewer pair using local handoff files, Claude subagents, and shared recruiting workflow skills without letting both agents edit the same files at once.
---

# Dual-Agent Orchestration

Use this skill when the user wants Codex and Claude to brainstorm, monitor each other, divide work, review each other's output, or coordinate across subagents.

## Default Roles

- Codex owns local execution: reading the repo, editing files, running tests, browser QA, git hygiene, and final verification.
- Claude owns long-form thinking: product/design strategy, architecture tradeoffs, UX critique, copy, broad review, and recruiting workflow strategy.
- Flip the roles only when the user explicitly starts the implementation in Claude Code or asks Claude to own a bounded task.

## Handoff Flow

1. Read `handoffs/README.md`.
2. Create a dated handoff file when the other agent needs to review or continue work.
3. Include goal, context, touched files, out-of-scope files, commands run, and exact questions.
4. Ask the receiving agent for ranked findings or a bounded implementation plan.
5. Apply only chosen changes, then verify locally.

## Claude Subagents

Use these Claude agents when available:

- `design-critic`: visual/UI/product review.
- `architecture-critic`: system design and refactor review.
- `recruiting-ops-reviewer`: application tracker, outreach, Gmail, and resume workflow review.
- `safety-gate`: pre-send, pre-submit, pre-push, and destructive-operation review.
- `handoff-router`: triage open handoffs and select the next owner.

## Output

Keep summaries operational:

- who owns the next step
- what files are in scope
- what risks were found
- what verification is required
- what needs human approval
