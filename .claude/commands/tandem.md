---
name: tandem
description: "Drive a coding task with BOTH Claude and Codex collaborating for better-planned, better-executed output. Invoke as $tandem or /tandem from either the Codex CLI/UI or Claude, in any repository. Whichever model you launch from becomes the driver; it pulls in the other model as its peer to (1) independently critique the plan, (2) optionally split or delegate implementation slices, and (3) review the final diff. Use for non-trivial or long-winded changes where a single model tends to drift, miss edge cases, or under-plan — e.g. 'I want this change in my fantasy-wizard repo and I want both models on it.'"
---

# Tandem (Claude + Codex pair-build)

Use this skill when the user wants two models working a task together instead of
one model working alone. It is repo-agnostic: it operates on the **current
working directory's repository** (e.g. fantasy-wizard), not on CodexSkills.

The goal is higher consistency and better output on longer tasks by using
**cross-model planning and review**: each model catches failure modes the other
misses, and a fresh second model reviewing the work resists the context-drift
that degrades a single long session.

## Operating Card

Before each phase, re-read `skills/tandem/OPERATING_CARD.md`. The card wins over
the prose below in any conflict.

## Roles: driver and peer

This skill is symmetric.

- **You are the DRIVER.** You are the model the user invoked (you already know
  whether you are Claude or Codex). You own the plan, the working tree, all
  edits, commits, and the final report.
- **Your PEER is the other model.** If you are Claude, your peer is Codex. If you
  are Codex, your peer is Claude. You consult the peer through one helper:

```bash
python3 skills/tandem/scripts/peer.py --from <claude|codex> --role <role> [options]
```

Pass `--from claude` if you are Claude, `--from codex` if you are Codex. The
helper invokes the opposite CLI (`codex exec` or `claude -p`) headlessly, prints
the peer's answer to stdout for you to read, and saves a transcript under
`/tmp/tandem/`. Read-only roles (`plan`, `critique`, `review`, `ask`) run the
peer with no write access; only `--role execute` lets the peer edit files.

If `peer.py` reports the peer CLI is missing, tell the user the other model's CLI
isn't installed and continue solo (still do the plan/critique/review phases
yourself, noting the peer was unavailable).

## Default workflow

Do not skip straight to editing. The value of this skill is the cross-model
loop. Work the current-directory repo.

### 1. Frame
- Restate the task in one or two sentences: what change, in which repo, success
  criteria, and hard constraints.
- Note `git status --short` and the current branch. Do not touch unrelated edits.
- Write the framed task to `/tmp/tandem/task.md` so the peer gets identical context.

### 2. Plan (driver drafts)
- Write a concise plan to `/tmp/tandem/plan.md`: ordered steps, files to touch,
  risks, and how you'll verify (tests/build/run).

### 3. Cross-critique (peer hardens the plan) — required
- Have the peer critique your plan:

```bash
python3 skills/tandem/scripts/peer.py --from <self> --role critique \
  --task-file /tmp/tandem/task.md --context-file /tmp/tandem/plan.md
```

- Read every peer finding. For each, **explicitly accept or reject it with a one-
  line reason.** Fold accepted MUST-FIX items into `/tmp/tandem/plan.md`.
- For a genuinely independent second opinion on hard tasks, you may also run
  `--role plan` first and reconcile the two plans before critiquing.

### 4. Implement
- Default to **single-implementer + cross-review**: you implement, the peer
  reviews. This avoids two agents editing the same tree at once.
- Work in checkpoints for long tasks. After each meaningful checkpoint, you may
  delegate a well-scoped, independent slice to the peer:

```bash
python3 skills/tandem/scripts/peer.py --from <self> --role execute \
  --task "Implement <one specific, isolated slice>. Touch only <files>."
```

  Only delegate slices that don't overlap files you're editing. After a delegated
  slice, re-read the changed files and reconcile before continuing.

### 5. Cross-review (peer reviews the diff) — required
- Have the peer review the actual diff:

```bash
python3 skills/tandem/scripts/peer.py --from <self> --role review --diff \
  --task-file /tmp/tandem/task.md
```

- Triage findings: fix every `[BUG]`, address or consciously dismiss `[RISK]`,
  use judgement on `[NIT]`. Note what you fixed vs deferred.

### 6. Verify
- Run the repo's real checks if they exist (tests, linters, type-check, build).
  Look for `package.json` scripts, `Makefile`, `scripts/check.sh`, CI config.
- For UI/runtime changes, run or build the app to confirm behavior when feasible.

### 7. Report
- Summarize: the hardened plan, which peer critique/review findings you accepted
  vs rejected (and why), what changed, verification results, and any follow-ups.
- Commit/push only if the user asked. Mirror their git conventions.

## When to delegate vs cross-review only

- **Cross-review only** (default): one coherent change, tightly coupled files, or
  anything where merge conflicts between two editors would be likely.
- **Delegate a slice with `--role execute`**: large tasks with clearly separable,
  non-overlapping parts (e.g. "peer writes the migration + tests while I wire the
  API"). Keep slices small and file-disjoint; you remain responsible for
  integrating and reviewing the peer's output.

## Long-run durability

For long or unattended tasks, keep `/tmp/tandem/` as the run record:
`task.md`, `plan.md`, and the timestamped `peer_*.out.md` transcripts. If the
session is interrupted, re-read those plus `git diff` to resume from the last
checkpoint instead of restarting.

## Guardrails

- Always do the cross-critique (step 3) and cross-review (step 5). They are the
  reason this skill exists; skipping them makes it just a normal solo run.
- Never run two editors on the same files simultaneously. Delegated slices must
  be file-disjoint from the driver's current work.
- Treat peer output as advice, not authority: accept or reject each finding with
  a reason. Do not blindly apply peer edits without reading them.
- Do not invent test results, confirmations, or peer findings. If the peer CLI is
  unavailable or times out, say so and continue solo.
- Do not touch unrelated working-tree changes. Commit/push only when asked.
- Operate on the current working directory's repo, never on CodexSkills unless
  that is explicitly the target.
