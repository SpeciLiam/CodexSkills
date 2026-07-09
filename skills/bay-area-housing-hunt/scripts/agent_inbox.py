#!/usr/bin/env python3
"""Agent inbox — the repo side of the dashboard's Agent panel.

The Vercel dashboard queues free-text requests ("add PadMapper", "the NOPA
listing is gone", "raise the group budget") into Supabase hh_config under
`agent_req:` keys (see housing-visualizer/src/agentStore.ts). This CLI is how
a Claude/Codex session — or a scheduled run — reads and answers them, closing
the loop back to the panel.

Usage:
  python3 agent_inbox.py list [--all] [--json]   # open requests (default) or everything
  python3 agent_inbox.py reply KEY "message"     # answer a request (status -> answered)
  python3 agent_inbox.py close KEY               # dismiss without an answer
  python3 agent_inbox.py submit "text"           # file a request from the CLI side

Stdlib-only (urllib), same public anon key as the dashboard (RLS-gated,
non-secret by design — this is a personal preferences store).
"""

from __future__ import annotations

import argparse
import json
import random
import string
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SB_URL = "https://kyqebsowglvzvncordtq.supabase.co"
SB_ANON = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imt5cWVic293Z2x2enZuY29yZHRxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgyNzY5MDksImV4cCI6MjA5Mzg1MjkwOX0."
    "Hd8A9H2ytvbLZM1LbIMpJZ8sgTFYdEb8DYW4YbD7q0I"
)
REST = f"{SB_URL}/rest/v1/hh_config"
PREFIX = "agent_req:"


def _headers(extra: dict | None = None) -> dict:
    h = {
        "apikey": SB_ANON,
        "Authorization": f"Bearer {SB_ANON}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def _request(url: str, method: str = "GET", body: dict | None = None, extra_headers: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=_headers(extra_headers))
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode() or "null"
        return json.loads(raw)


def fetch_requests() -> list[dict]:
    """All agent_req rows, newest key first, flattened to {key, text, status, ...}."""
    q = urllib.parse.quote(f"{PREFIX}*", safe="*:")
    rows = _request(f"{REST}?key=like.{q}&select=key,value,updated_at&order=key.desc&limit=100")
    out = []
    for row in rows:
        v = row.get("value") or {}
        if isinstance(v, dict) and v.get("text"):
            out.append({"key": row["key"], "updated_at": row.get("updated_at"), **v})
    return out


def upsert(key: str, value: dict) -> None:
    _request(
        REST,
        method="POST",
        body={"key": key, "value": value, "updated_at": datetime.now(timezone.utc).isoformat()},
        extra_headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
    )


def build_reply_value(existing: dict, reply: str) -> dict:
    """Pure: existing request value + a reply -> the answered value written back."""
    return {
        "text": existing.get("text", ""),
        "status": "answered",
        "reply": reply,
        "created": existing.get("created", ""),
        "answeredAt": datetime.now(timezone.utc).isoformat(),
    }


def build_closed_value(existing: dict) -> dict:
    out = {k: existing[k] for k in ("text", "reply", "created", "answeredAt") if existing.get(k)}
    out["status"] = "closed"
    return out


def new_key(now: datetime | None = None) -> str:
    """Sortable agent_req key matching the dashboard's format."""
    ts = (now or datetime.now(timezone.utc)).strftime("%Y%m%d%H%M%S")
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{PREFIX}{ts}-{suffix}"


def find(reqs: list[dict], key: str) -> dict | None:
    # Accept the full key or any unambiguous suffix/substring for CLI ergonomics.
    exact = [r for r in reqs if r["key"] == key or r["key"] == PREFIX + key]
    if exact:
        return exact[0]
    part = [r for r in reqs if key in r["key"]]
    return part[0] if len(part) == 1 else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    p_list = sub.add_parser("list", help="show requests (open only by default)")
    p_list.add_argument("--all", action="store_true", help="include answered/closed")
    p_list.add_argument("--json", action="store_true", help="machine-readable output")
    p_reply = sub.add_parser("reply", help="answer a request")
    p_reply.add_argument("key")
    p_reply.add_argument("message")
    p_close = sub.add_parser("close", help="dismiss a request")
    p_close.add_argument("key")
    p_submit = sub.add_parser("submit", help="file a request from the CLI")
    p_submit.add_argument("text")
    args = ap.parse_args(argv)
    cmd = args.cmd or "list"

    if cmd == "list":
        reqs = fetch_requests()
        show_all = getattr(args, "all", False)
        if not show_all:
            reqs = [r for r in reqs if r.get("status") == "open"]
        if getattr(args, "json", False):
            print(json.dumps(reqs, indent=2))
        elif not reqs:
            print("No open agent requests." if not show_all else "No agent requests.")
        else:
            for r in reqs:
                print(f"[{r.get('status','?'):8s}] {r['key']}")
                print(f"           {r.get('text','')}")
                if r.get("reply"):
                    print(f"           ↳ {r['reply']}")
        return 0

    if cmd in ("reply", "close"):
        reqs = fetch_requests()
        req = find(reqs, args.key)
        if not req:
            print(f"No unique request matching '{args.key}'. Run `agent_inbox.py list --all`.", file=sys.stderr)
            return 1
        value = build_reply_value(req, args.message) if cmd == "reply" else build_closed_value(req)
        upsert(req["key"], value)
        print(f"{req['key']} -> {value['status']}")
        return 0

    if cmd == "submit":
        key = new_key()
        upsert(key, {"text": args.text, "status": "open", "created": datetime.now(timezone.utc).isoformat()})
        print(key)
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
