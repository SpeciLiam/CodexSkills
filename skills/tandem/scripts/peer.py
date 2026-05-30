#!/usr/bin/env python3
"""Consult the *other* model from inside a tandem run.

`tandem` is symmetric: it can be driven by Claude (via `claude`) or by Codex
(via `codex exec`). Whichever model is driving calls this helper to hand a
scoped sub-task (plan critique, diff review, a delegated implementation slice,
or a plain question) to its peer model, then reads the peer's answer back.

Usage (the driver knows which model it is and passes --from):

    python3 peer.py --from claude  --role critique --context-file /tmp/tandem/plan.md \
        --task "Critique this plan for the change described below" --task-file /tmp/tandem/task.md

    python3 peer.py --from codex   --role review   --diff \
        --task "Review this diff for correctness bugs and missing cases"

Roles:
  plan      ask the peer to draft an independent plan for the task
  critique  ask the peer to find risks/gaps/alternatives in OUR plan
  review    ask the peer to review a diff for bugs and missing cases
  execute   delegate an implementation slice to the peer (peer may edit files)
  ask       free-form question to the peer

The peer's stdout is printed to this process's stdout (so the driver model
sees it) and saved under /tmp/tandem/ for the run record.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TANDEM_DIR = Path(os.environ.get("TANDEM_DIR", "/tmp/tandem"))

# Read-only roles must not let the peer edit the working tree.
READ_ONLY_ROLES = {"plan", "critique", "review", "ask"}

ROLE_FRAMING = {
    "plan": (
        "You are the PEER model in a two-model (Claude + Codex) tandem session. "
        "Draft your own independent, concise implementation plan for the task "
        "below. Do NOT edit any files. Return: ordered steps, key files to "
        "touch, risks, and anything the other model is likely to miss."
    ),
    "critique": (
        "You are the PEER reviewer in a two-model (Claude + Codex) tandem "
        "session. The other model wrote the plan in the CONTEXT below. Do NOT "
        "edit any files. Adversarially critique the plan: concrete gaps, wrong "
        "assumptions, missing edge cases, simpler alternatives, and ordering "
        "problems. Be specific and terse. End with a short prioritized list of "
        "MUST-FIX vs NICE-TO-HAVE changes."
    ),
    "review": (
        "You are the PEER reviewer in a two-model (Claude + Codex) tandem "
        "session. Review the diff/CONTEXT below for correctness bugs, broken "
        "edge cases, security issues, and anything that does not match the "
        "stated task. Do NOT edit any files. Return findings as a short list, "
        "each tagged [BUG] / [RISK] / [NIT], with file:line where possible. If "
        "it looks correct, say so plainly."
    ),
    "execute": (
        "You are the PEER implementer in a two-model (Claude + Codex) tandem "
        "session. Implement ONLY the slice described below in the current "
        "repository. Make the smallest correct change, do not refactor "
        "unrelated code, and end by summarizing exactly which files you changed "
        "and why."
    ),
    "ask": (
        "You are the PEER model in a two-model (Claude + Codex) tandem session. "
        "Answer the question below concisely and concretely."
    ),
}


def now_tag() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def detect_self() -> str | None:
    """Best-effort guess of which model is driving, if --from is omitted."""
    env = os.environ
    if any(k.startswith("CLAUDE") or k == "CLAUDECODE" for k in env):
        return "claude"
    if any(k.startswith("CODEX") for k in env):
        return "codex"
    return None


def build_prompt(role: str, task: str, context: str) -> str:
    parts = [ROLE_FRAMING[role], "", "## TASK", task.strip()]
    if context.strip():
        parts += ["", "## CONTEXT", context.strip()]
    return "\n".join(parts) + "\n"


def gather_context(args: argparse.Namespace) -> str:
    chunks: list[str] = []
    if args.context_file:
        p = Path(args.context_file)
        if p.exists():
            chunks.append(p.read_text(encoding="utf-8", errors="replace"))
    if args.diff:
        repo = str(args.repo)
        # Include both staged and unstaged changes against HEAD.
        diff = subprocess.run(
            ["git", "-C", repo, "diff", "HEAD"],
            capture_output=True, text=True,
        )
        if diff.returncode == 0 and diff.stdout.strip():
            chunks.append("```diff\n" + diff.stdout + "\n```")
        else:
            chunks.append("(no diff against HEAD)")
    if args.context:
        chunks.append(args.context)
    return "\n\n".join(chunks)


def build_codex_cmd(prompt_file: Path, args: argparse.Namespace) -> list[str]:
    sandbox = "read-only" if args.role in READ_ONLY_ROLES else (args.sandbox or "workspace-write")
    cmd = [
        "codex", "exec",
        "--ephemeral",
        "--cd", str(args.repo),
        "--sandbox", sandbox,
    ]
    if args.model:
        cmd += ["-m", args.model]
    cmd += ["-c", f'model_reasoning_effort="{args.reasoning}"']
    # Codex exec reads the prompt from stdin when given "-".
    cmd += ["-"]
    return cmd


def build_claude_cmd(args: argparse.Namespace) -> list[str]:
    perm = "plan" if args.role in READ_ONLY_ROLES else (args.permission or "acceptEdits")
    cmd = ["claude", "-p", "--permission-mode", perm, "--add-dir", str(args.repo)]
    if args.model:
        cmd += ["--model", args.model]
    return cmd


def main() -> int:
    ap = argparse.ArgumentParser(description="Consult the peer model in a tandem run.")
    ap.add_argument("--from", dest="from_model", choices=["claude", "codex"],
                    help="Which model is driving (the peer is the other one). Auto-detected if omitted.")
    ap.add_argument("--role", choices=list(ROLE_FRAMING), default="ask")
    ap.add_argument("--task", default="", help="The instruction/question for the peer.")
    ap.add_argument("--task-file", help="File whose contents are appended to --task.")
    ap.add_argument("--context", default="", help="Inline extra context.")
    ap.add_argument("--context-file", help="File to include as context (e.g. the plan).")
    ap.add_argument("--diff", action="store_true", help="Include `git diff HEAD` as context.")
    ap.add_argument("--repo", default=os.getcwd(), help="Repo/working dir for the peer (default: cwd).")
    ap.add_argument("--model", help="Override the peer model id.")
    ap.add_argument("--reasoning", default="high", help="Codex reasoning effort (default: high).")
    ap.add_argument("--sandbox", help="Codex sandbox for execute role (default: workspace-write).")
    ap.add_argument("--permission", help="Claude permission-mode for execute role (default: acceptEdits).")
    ap.add_argument("--timeout", type=int, default=1800, help="Peer timeout in seconds (default: 1800).")
    ap.add_argument("--dry-run", action="store_true", help="Print the command and prompt, do not run.")
    args = ap.parse_args()

    self_model = args.from_model or detect_self()
    if self_model is None:
        print("ERROR: could not detect the driving model. Pass --from claude|codex.", file=sys.stderr)
        return 2
    peer = "codex" if self_model == "claude" else "claude"

    if not args.dry_run and not shutil.which(peer):
        print(f"ERROR: peer CLI '{peer}' not found on PATH. Install it or run the "
              f"other side manually.", file=sys.stderr)
        return 3

    task = args.task
    if args.task_file and Path(args.task_file).exists():
        task = (task + "\n\n" + Path(args.task_file).read_text(encoding="utf-8", errors="replace")).strip()
    if not task:
        print("ERROR: no task provided (use --task and/or --task-file).", file=sys.stderr)
        return 2

    context = gather_context(args)
    prompt = build_prompt(args.role, task, context)

    TANDEM_DIR.mkdir(parents=True, exist_ok=True)
    tag = now_tag()
    prompt_file = TANDEM_DIR / f"peer_{peer}_{args.role}_{tag}.prompt.md"
    out_file = TANDEM_DIR / f"peer_{peer}_{args.role}_{tag}.out.md"
    prompt_file.write_text(prompt, encoding="utf-8")

    if peer == "codex":
        cmd = build_codex_cmd(prompt_file, args)
        stdin_data = prompt
    else:
        cmd = build_claude_cmd(args)
        stdin_data = prompt

    print(f"[tandem] {self_model} -> {peer} | role={args.role} | repo={args.repo}", file=sys.stderr)
    print(f"[tandem] prompt saved: {prompt_file}", file=sys.stderr)
    if args.dry_run:
        print("[tandem] DRY RUN command:", " ".join(cmd), file=sys.stderr)
        print(prompt)
        return 0

    try:
        proc = subprocess.run(
            cmd, input=stdin_data, capture_output=True, text=True, timeout=args.timeout,
        )
    except subprocess.TimeoutExpired:
        print(f"[tandem] ERROR: peer '{peer}' timed out after {args.timeout}s.", file=sys.stderr)
        return 124

    output = proc.stdout or ""
    if proc.returncode != 0:
        print(f"[tandem] peer '{peer}' exited {proc.returncode}.", file=sys.stderr)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)
    out_file.write_text(output + ("\n\n--- stderr ---\n" + proc.stderr if proc.stderr else ""),
                        encoding="utf-8")
    print(f"[tandem] peer output saved: {out_file}", file=sys.stderr)
    # The driver model reads the peer answer from stdout.
    print(output)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
