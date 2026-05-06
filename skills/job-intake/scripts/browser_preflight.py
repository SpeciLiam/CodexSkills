#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class AppleScriptResult:
    ok: bool
    stdout: str
    stderr: str


def run_osascript(script: str, timeout: int = 5) -> AppleScriptResult:
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return AppleScriptResult(False, exc.stdout or "", "timed out")

    return AppleScriptResult(
        result.returncode == 0,
        result.stdout.strip(),
        result.stderr.strip(),
    )


def describe_failure(result: AppleScriptResult) -> str:
    detail = result.stderr or result.stdout or "no diagnostic output"
    if "-1743" in detail:
        return f"{detail} (macOS Automation permission denied)"
    if "-10827" in detail:
        return f"{detail} (macOS cannot grant this process access to System Events)"
    if "-1719" in detail:
        return f"{detail} (target app is not available or not scriptable)"
    return detail


def can_query_processes() -> tuple[bool, str]:
    result = run_osascript('tell application "System Events" to count processes')
    if result.ok:
        return True, result.stdout
    return False, describe_failure(result)


def is_running(app_name: str) -> tuple[bool, str]:
    result = run_osascript(
        f'tell application "System Events" to (name of processes) contains "{app_name}"'
    )
    if result.ok:
        return result.stdout == "true", result.stdout
    return False, describe_failure(result)


def can_talk_to_browser(app_name: str) -> tuple[bool, str]:
    if app_name == "Google Chrome":
        script = 'tell application "Google Chrome" to count windows'
    elif app_name == "Firefox":
        # Firefox exposes a smaller AppleScript surface than Chrome. Asking for
        # the app name still verifies that Apple Events can reach it.
        script = 'tell application "Firefox" to name'
    else:
        script = f'tell application "{app_name}" to name'

    result = run_osascript(script)
    if result.ok:
        return True, result.stdout
    return False, describe_failure(result)


def frontmost_app() -> str:
    result = run_osascript(
        'tell application "System Events" to name of first process whose frontmost is true'
    )
    if result.ok:
        return result.stdout
    return ""


def main() -> int:
    process_query_ok, process_query_detail = can_query_processes()
    if not process_query_ok:
        print(f"BLOCKED: System Events unavailable: {process_query_detail}")
        print("HINT: grant Automation/Accessibility permissions to the Codex automation runner.")
        return 1

    failures = []
    for app_name in ("Google Chrome", "Firefox"):
        running, running_detail = is_running(app_name)
        if not running:
            failures.append(f"{app_name}: not running ({running_detail})")
            continue

        browser_ok, browser_detail = can_talk_to_browser(app_name)
        if browser_ok:
            active = frontmost_app()
            suffix = f"; frontmost={active}" if active else ""
            print(f"READY: {app_name}; browser_probe={browser_detail or 'ok'}{suffix}")
            return 0

        failures.append(f"{app_name}: Apple Events denied: {browser_detail}")

    print("BLOCKED: no supported browser automation target ready")
    for failure in failures:
        print(f"- {failure}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
