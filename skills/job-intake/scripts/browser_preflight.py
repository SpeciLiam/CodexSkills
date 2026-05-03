#!/usr/bin/env python3
from __future__ import annotations

import subprocess


def check(app_name: str) -> bool:
    result = subprocess.run(
        ["osascript", "-e", f'tell application "System Events" to (name of processes) contains "{app_name}"'],
        capture_output=True,
        text=True,
        timeout=5,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def main() -> int:
    for app_name in ("Google Chrome", "Firefox"):
        if check(app_name):
            print(f"READY: {app_name}")
            return 0
    print("BLOCKED: no supported browser running")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
