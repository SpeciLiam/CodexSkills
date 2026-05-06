#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[3]
CAPTURE_DIR = Path("/tmp/codexskills-job-intake")
API_BASE = "https://api.apify.com/v2"
TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}
SOURCES = ("linkedin", "greenhouse")


def read_json(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    data = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return data


def request_json(
    method: str,
    path: str,
    token: str,
    body: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
) -> dict[str, Any] | list[Any]:
    url = f"{API_BASE}{path}"
    if query:
        url = f"{url}?{urlencode({key: value for key, value in query.items() if value is not None})}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=60) as response:
            text = response.read().decode("utf-8")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Apify API {error.code} for {path}: {detail}") from error
    except URLError as error:
        raise SystemExit(f"Apify API request failed for {path}: {error}") from error
    return json.loads(text) if text.strip() else {}


def data(response: dict[str, Any] | list[Any]) -> Any:
    if isinstance(response, dict) and "data" in response:
        return response["data"]
    return response


def resource_id(value: str) -> str:
    return quote(value.strip().replace("/", "~"), safe="~")


def start_run(source: str, args: argparse.Namespace, token: str) -> dict[str, Any]:
    task_id = getattr(args, f"{source}_task")
    actor_id = getattr(args, f"{source}_actor")
    actor_input = read_json(getattr(args, f"{source}_input_json"))
    if task_id:
        return data(request_json("POST", f"/actor-tasks/{resource_id(task_id)}/runs", token))
    if actor_id:
        return data(request_json("POST", f"/acts/{resource_id(actor_id)}/runs", token, actor_input))
    raise SystemExit(f"No Apify task or actor configured for {source}")


def wait_for_run(run_id: str, token: str, timeout_seconds: int, poll_interval: int) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    while True:
        run = data(request_json("GET", f"/actor-runs/{resource_id(run_id)}", token))
        status = str(run.get("status", ""))
        if status in TERMINAL_STATUSES:
            if status != "SUCCEEDED":
                raise SystemExit(f"Apify run {run_id} ended with status {status}")
            return run
        if time.time() >= deadline:
            raise SystemExit(f"Timed out waiting for Apify run {run_id}; last status {status or 'UNKNOWN'}")
        time.sleep(max(1, poll_interval))


def get_items(dataset_id: str, token: str, limit: int | None) -> list[dict[str, Any]]:
    items = data(
        request_json(
            "GET",
            f"/datasets/{resource_id(dataset_id)}/items",
            token,
            query={"clean": "true", "format": "json", "limit": limit},
        )
    )
    if not isinstance(items, list):
        raise SystemExit(f"Dataset {dataset_id} did not return a JSON array")
    return [item for item in items if isinstance(item, dict)]


def write_capture(source: str, items: list[dict[str, Any]], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{source}_jobs.json"
    path.write_text(json.dumps(items, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def run_listener(sources: list[str], dry_run: bool) -> int:
    command = [sys.executable, str(ROOT / "skills" / "job-intake" / "scripts" / "run_job_listener.py"), "--sources", *sources]
    if dry_run:
        command.append("--dry-run")
    import subprocess

    result = subprocess.run(command, cwd=ROOT)
    return result.returncode


def configured_sources(args: argparse.Namespace) -> list[str]:
    selected = args.sources or list(SOURCES)
    return [
        source
        for source in selected
        if getattr(args, f"{source}_task") or getattr(args, f"{source}_actor")
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture LinkedIn/Greenhouse jobs through Apify and feed job-intake.")
    parser.add_argument("--sources", nargs="+", choices=SOURCES, help="Sources to capture. Defaults to all configured sources.")
    parser.add_argument("--output-dir", default=str(CAPTURE_DIR), help="Directory for *_jobs.json listener inputs.")
    parser.add_argument("--timeout-seconds", type=int, default=900, help="Maximum wait per Apify run.")
    parser.add_argument("--poll-interval", type=int, default=10, help="Seconds between Apify run status checks.")
    parser.add_argument("--max-items", type=int, help="Maximum dataset items to download per source.")
    parser.add_argument("--no-listener", action="store_true", help="Only write capture files; do not update job-intake.md.")
    parser.add_argument("--dry-run-listener", action="store_true", help="Run listener in dry-run mode after capture.")
    parser.add_argument("--linkedin-task", default=os.environ.get("APIFY_LINKEDIN_TASK_ID"))
    parser.add_argument("--linkedin-actor", default=os.environ.get("APIFY_LINKEDIN_ACTOR_ID"))
    parser.add_argument("--linkedin-input-json", default=os.environ.get("APIFY_LINKEDIN_INPUT_JSON"))
    parser.add_argument("--greenhouse-task", default=os.environ.get("APIFY_GREENHOUSE_TASK_ID"))
    parser.add_argument("--greenhouse-actor", default=os.environ.get("APIFY_GREENHOUSE_ACTOR_ID"))
    parser.add_argument("--greenhouse-input-json", default=os.environ.get("APIFY_GREENHOUSE_INPUT_JSON"))
    args = parser.parse_args()

    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token:
        raise SystemExit("Set APIFY_TOKEN before running Apify capture.")
    sources = configured_sources(args)
    if not sources:
        raise SystemExit("No Apify sources configured. Set APIFY_*_TASK_ID or APIFY_*_ACTOR_ID.")

    output_dir = Path(args.output_dir).expanduser()
    for source in sources:
        run = start_run(source, args, token)
        run_id = str(run.get("id", ""))
        if not run_id:
            raise SystemExit(f"Apify did not return a run id for {source}")
        print(f"STARTED {source}: {run_id}")
        finished = wait_for_run(run_id, token, args.timeout_seconds, args.poll_interval)
        dataset_id = str(finished.get("defaultDatasetId", ""))
        if not dataset_id:
            raise SystemExit(f"Apify run {run_id} has no default dataset")
        items = get_items(dataset_id, token, args.max_items)
        path = write_capture(source, items, output_dir)
        print(f"CAPTURED {source}: {len(items)} items -> {path}")

    if args.no_listener:
        return 0
    return run_listener(sources, args.dry_run_listener)


if __name__ == "__main__":
    raise SystemExit(main())
