#!/usr/bin/env python3

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import subprocess
import sys


SCRIPT_DIR = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Record a LinkedIn outreach outcome for any registered lane.")
    parser.add_argument("--contact-type", required=True)
    parser.add_argument("--posting-key", required=True)
    parser.add_argument("--outcome", choices=("sent", "connected", "replied", "declined", "skipped", "blocked"), required=True)
    parser.add_argument("--company", default="")
    parser.add_argument("--role", default="")
    parser.add_argument("--contact-name", default="")
    parser.add_argument("--profile-url", default="")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--root", default=None)
    args = parser.parse_args()

    if args.outcome != "sent":
        print(f"Outcome '{args.outcome}' noted; tracker row updates are currently written for sent invites only.")
        return 0

    if not args.company or not args.contact_name:
        raise SystemExit("--company and --contact-name are required when --outcome sent updates the application tracker.")

    command = [
        sys.executable,
        str(SCRIPT_DIR / "update_outreach_tracker.py"),
        "--company",
        args.company,
        "--posting-key",
        args.posting_key,
        "--contact-name",
        args.contact_name,
        "--profile-url",
        args.profile_url,
        "--contact-type",
        args.contact_type,
        "--date",
        args.date,
    ]
    if args.role:
        command.extend(["--role", args.role])
    if args.root:
        command.extend(["--root", args.root])
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
