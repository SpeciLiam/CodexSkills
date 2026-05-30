# Claude Code Project Guide

This repo is shared with Codex. Treat Claude as a planning, design, critique, and long-running reasoning partner unless the user explicitly asks Claude to execute a repo change.

## Two-Agent Rule

- One agent edits at a time. If Codex is implementing, Claude reviews or drafts plans only.
- Use `handoffs/` for cross-agent context. Read `handoffs/README.md` before creating or answering a handoff.
- Do not assume Codex has Claude memory or Claude has Codex memory. Put the minimum needed context in the handoff file.
- Prefer concrete review findings over broad rewrites. Rank issues by severity and include file paths when possible.
- For recruiting workflows, use the existing slash commands generated from `skills/*/SKILL.md`.

## Default Division

- Codex: local repo execution, tests, browser verification, final patching, git hygiene.
- Claude: ambiguous product/design thinking, UX copy, long-form spec work, adversarial review, recruiting workflow critique, and subagent exploration.
- Either agent may execute when the user explicitly asks, but the other agent should then act as reviewer.

## Safety

- Never send external messages, submit applications, or update public systems without explicit user approval.
- Do not run destructive git commands such as `reset --hard`, force pushes, branch deletion, or broad cleanup unless the user explicitly requested that exact action.
- Preserve user edits. Dirty files are assumed to belong to the user or another agent.
