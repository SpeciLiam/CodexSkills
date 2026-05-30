# Codex Project Guide

This repo is shared with Claude Code. Use this file as the Codex-facing companion to `CLAUDE.md`.

## Two-Agent Rule

- Codex should usually own implementation, command execution, tests, browser checks, and final patching.
- Ask Claude for long-form design review, UX critique, architecture tradeoffs, adversarial code review, or recruiting workflow strategy when the task is broad or subjective.
- Use `handoffs/` to pass context between agents. Read `handoffs/README.md` before creating or answering a handoff.
- One agent edits at a time. If Claude has an active implementation pass, Codex reviews and plans only until control is handed back.

## Review Standard

When reviewing Claude output, lead with concrete risks: bugs, missing states, bad assumptions, safety issues, tracker corruption risks, or UX problems. Avoid restating the whole plan.

## Recruiting Workflows

Prefer the local skills in `skills/` and their scripts. Keep markdown trackers as the source of truth, refresh generated visualizer data only after tracker changes, and keep Notion sync opt-in.
