# Tandem Usage

Use this reference when Liam asks for the LinkedIn apply-all workflow to run with
Claude and Codex together.

## Worker / Monitor Roles

- The worker owns Chrome, application forms, resume generation, tracker/cache
  edits, validation, and the final report.
- The monitor is the opposite model from the worker. It critiques the plan,
  reviews duplicate criteria and guardrails, reviews tracker diffs, and flags
  missing safety checks.

Choose the split from where the workflow starts:

- Started from Codex: Codex worker, Claude monitor.
- Started from Claude: Claude worker, Codex monitor.
- Explicit user override: use the requested worker/monitor split.

Do not split live browser control. Only one agent should operate LinkedIn,
Chrome, ATS pages, uploads, tracker edits, and cache refreshes.

## Start Pattern

From the CodexSkills repo:

```bash
mkdir -p /tmp/tandem
```

Write `/tmp/tandem/task.md` with the target LinkedIn search URL, max job count if
any, and the success criteria. Write `/tmp/tandem/plan.md` with the proposed
search, duplicate keys, browser lane, application guardrails, tracker write
policy, and verification.

If Codex is the worker, ask Claude for a read-only critique:

```bash
python3 skills/tandem/scripts/peer.py --from codex --role critique \
  --task-file /tmp/tandem/task.md \
  --context-file /tmp/tandem/plan.md
```

If Claude is the worker, ask Codex for the same critique with `--from claude`.
Accept or reject each monitor finding with a reason, then update the plan before
opening Chrome.

## During The Run

Keep a durable state file such as `/tmp/linkedin_apply_all_state.json`. After
each durable job outcome, record:

- company and role
- LinkedIn job URL/id
- duplicate/apply/manual/archive status
- resume PDF path if generated or reused
- confirmation evidence or blocker
- tracker/cache files changed
- timestamp

If the run becomes long or context-heavy, finish the current job, refresh cache,
write the state file, and pause with a concise handoff rather than pushing into
the next application from degraded context.

## Review Pattern

Before reporting done, ask the monitor to review the actual diff. From Codex:

```bash
python3 skills/tandem/scripts/peer.py --from codex --role review --diff \
  --task-file /tmp/tandem/task.md
```

From Claude, use the same command with `--from claude`.

Fix every `[BUG]`, address or explicitly dismiss `[RISK]`, and use judgment on
`[NIT]`. Report what was accepted, rejected, and why.

## Hard Rules

- Do not let the monitor submit applications, answer forms, upload files, or
  control Chrome during the same run.
- Do not let both agents edit `application-trackers/` or generated visualizer
  data simultaneously.
- Do not ask the monitor to invent missing facts about jobs, confirmations, or
  application statuses. All status changes need live evidence from Codex's
  browser run, Claude's browser run, or tracker/email evidence captured by the
  active worker.
- Do not commit or push unless Liam explicitly asks or a referenced recruiting
  skill's standing policy requires it for that run.
