#!/usr/bin/env python3
"""Bay Area housing hunt — single kickoff entrypoint.

Agent-agnostic: run by a human, by Codex, or by Claude. It does everything that
can be done deterministically and offline, runs the safe headless capture tiers
(Craigslist public sapi JSON, Zumper public SSR state, and configured APIs), rebuilds
the ledger + power rankings, and then prints a precise AI-CAPTURE PLAN for the
sources that need a visible/logged-in browser. The conductor fulfils that plan with:

  - Codex  -> Chrome plugin (or Computer Use fallback)
  - Claude -> Claude-in-Chrome / Computer Use

by writing capture JSON files (schema in references/sources.md) into the capture
dir, then re-running this script. Same script, same files, either agent.

Typical use:
    python3 run.py                 # headless capture + score + print AI plan
    python3 run.py --sources craigslist zillow facebook
                                   # run/plan only selected configured sources
    python3 run.py --list-sources  # show selectable configured sources
    python3 run.py --fresh-capture-dir
                                   # scheduled-run kickoff; avoids stale AI files
    python3 run.py --no-network    # skip the network fetch (offline / blocked)
    python3 run.py --plan-only      # just print what AI capture is needed
    python3 run.py --input cap.json # also ingest a hand/AI-produced capture file

Browser/AI capture is intentionally NOT done here — a plain script cannot drive
the Chrome plugin or Computer Use; those are conductor tools. This script tells
the conductor exactly what to capture and where to put it.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import housing_pipeline as hp
import capture_api
import capture_web

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CAPTURE_DIR = Path("/tmp/codexskills-housing-hunt")
SEARCHES_FILE = SCRIPT_DIR / "searches.json"
USER_AGENT = "CodexSkills-housing-hunt/1.0 (personal housing search; contact via repo owner)"
FETCH_TIMEOUT = 12
SOURCE_TIERS = ("web", "rss", "apis", "ai_browser")
SOURCE_ALIASES = {
    "all": {"all"},
    "cl": {"craigslist"},
    "craig": {"craigslist"},
    "craigs": {"craigslist"},
    "cragislist": {"craigslist"},
    "craiglist": {"craigslist"},
    "craigslist": {"craigslist"},
    "fb": {"facebook"},
    "faceb": {"facebook"},
    "facebook": {"facebook"},
    "marketplace": {"marketplace"},
    "zillow": {"zillow"},
    "zumper": {"zumper"},
    "apartments": {"apartments"},
    "apartments.com": {"apartments"},
    "apts": {"apartments"},
    "furnished": {"furnished"},
    "furnishedfinder": {"furnished"},
    "furnished-finder": {"furnished"},
    "reddit": {"reddit"},
    "rentcast": {"rentcast"},
}


def load_searches() -> dict:
    if not SEARCHES_FILE.exists():
        return {"web": [], "rss": [], "apis": [], "ai_browser": []}
    try:
        return json.loads(SEARCHES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        print(f"WARNING: could not read {SEARCHES_FILE.name} ({exc}); proceeding with no configured sources", file=sys.stderr)
        return {"web": [], "rss": [], "apis": [], "ai_browser": []}


def _source_slug(value: str) -> str:
    return hp.slug(value).replace("-", "")


def parse_source_filters(raw: str | list[str]) -> set[str]:
    """Normalize a comma/space-separated --sources string into match tokens."""
    if isinstance(raw, list):
        text = " ".join(str(item) for item in raw if str(item).strip())
    else:
        text = (raw or "all").strip()
    if not text:
        return {"all"}
    out: set[str] = set()
    for part in text.replace(",", " ").split():
        key = part.strip().lower()
        if not key:
            continue
        out.update(SOURCE_ALIASES.get(key, {_source_slug(key)}))
    return out or {"all"}


def source_tokens(cfg: dict) -> set[str]:
    """Searchable tokens for one configured source row.

    Users think in portals ("craigslist"), products ("facebook"), and sometimes
    exact labels ("sf-sublets"), so keep product tokens broad and label tokens exact.
    """
    values: list[str] = []
    for key in ("name", "kind", "source"):
        value = cfg.get(key)
        if isinstance(value, str):
            values.append(value)
    label = cfg.get("label")
    if isinstance(label, str) and label.strip():
        values.append(label)
    tokens: set[str] = set()
    url_values = [cfg.get(key) for key in ("search_url", "url")]
    joined = " ".join(
        value for value in [*values, *(v for v in url_values if isinstance(v, str))]
    ).lower()
    for value in values:
        tokens.add(_source_slug(value))
    # Source names/kinds are also selectable by word; labels stay exact so a generic
    # word like "apartments" does not accidentally select every apartment category.
    for key in ("name", "source"):
        value = cfg.get(key)
        if isinstance(value, str):
            for chunk in value.replace("/", " ").replace("_", " ").replace("-", " ").split():
                tokens.add(_source_slug(chunk))
    if "facebook" in joined:
        tokens.add("facebook")
    if "craigslist" in joined or "sapi.craigslist" in joined:
        tokens.add("craigslist")
    if "zillow" in joined:
        tokens.add("zillow")
    if "apartments.com" in joined:
        tokens.add("apartments")
    if "zumper" in joined:
        tokens.add("zumper")
    if "furnished finder" in joined or "furnishedfinder" in joined:
        tokens.add("furnished")
    if "reddit" in joined:
        tokens.add("reddit")
    if "rentcast" in joined:
        tokens.add("rentcast")
    return tokens


def source_matches(cfg: dict, filters: set[str]) -> bool:
    if "all" in filters:
        return True
    tokens = source_tokens(cfg)
    return any(wanted in tokens for wanted in filters)


def filter_searches(searches: dict, raw_sources: str | list[str]) -> tuple[dict, set[str]]:
    filters = parse_source_filters(raw_sources)
    if "all" in filters:
        return searches, filters
    filtered = copy.deepcopy(searches)
    for tier in SOURCE_TIERS:
        filtered[tier] = [
            cfg for cfg in searches.get(tier, [])
            if isinstance(cfg, dict) and source_matches(cfg, filters)
        ]
    return filtered, filters


def selected_source_counts(searches: dict) -> dict[str, int]:
    return {tier: len(searches.get(tier, [])) for tier in SOURCE_TIERS}


def source_display_name(cfg: dict) -> str:
    parts = [hp.clean(cfg.get("name", ""))]
    label = hp.clean(cfg.get("label", ""))
    if label:
        parts.append(f"[{label}]")
    return " ".join(part for part in parts if part).strip() or "unnamed source"


def list_configured_sources(searches: dict) -> None:
    print("Selectable configured sources:")
    for tier in SOURCE_TIERS:
        rows = searches.get(tier, [])
        if not rows:
            continue
        print(f"\n{tier}:")
        for cfg in rows:
            if not isinstance(cfg, dict):
                continue
            aliases = ", ".join(sorted(source_tokens(cfg))[:12])
            print(f"  - {source_display_name(cfg)}")
            if aliases:
                print(f"    tokens: {aliases}")


def capture_path_matches(path: Path, filters: set[str]) -> bool:
    """Filter scratch capture files by selected source tokens.

    Explicit --input files are still honored, but the capture-dir glob should not
    pull stale unselected source files into a narrowed run.
    """
    if "all" in filters:
        return True
    stem = hp.slug(path.stem)
    compact = stem.replace("-", "")
    path_tokens = {compact, *(part for part in stem.split("-") if part)}
    for wanted in filters:
        if wanted in path_tokens:
            return True
        if wanted in compact:
            return True
    return False


def _rss_url(url: str) -> str:
    parts = urlparse(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if query.get("format") == "rss":
        return url
    query["format"] = "rss"
    return urlunparse(parts._replace(query=urlencode(query)))


def _text(node, *suffixes) -> str:
    for child in node.iter():
        tag = child.tag.split("}")[-1].lower()
        if tag in suffixes and (child.text or "").strip():
            return child.text.strip()
    return ""


def fetch_rss(name: str, url: str, market_hint: str) -> tuple[list[dict], str | None]:
    """Fetch one public RSS feed. Returns (records, error). On any failure we
    return a Source-Blocked record and the error string — never a retry, proxy,
    or bypass (that is a hard rule in references/sources.md)."""
    feed_url = _rss_url(url)
    req = urllib.request.Request(feed_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            if resp.status != 200:
                raise urllib.error.HTTPError(feed_url, resp.status, "non-200", resp.headers, None)
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 - any failure -> blocked, by design
        reason = f"Source Blocked: {type(exc).__name__}: {exc}"
        return ([{
            "source": name,
            "status": "source blocked",
            "title": f"{name} feed unreachable",
            "url": feed_url,
            "description": reason,
            "market": market_hint,
        }], reason)

    try:
        records = parse_rss_body(body, name, market_hint)
    except ET.ParseError as exc:
        return ([{
            "source": name,
            "status": "source blocked",
            "title": f"{name} feed unparseable",
            "url": feed_url,
            "description": f"Source Blocked: ParseError: {exc}",
            "market": market_hint,
        }], f"parse error: {exc}")
    return records, None


def parse_rss_body(body: str, name: str, market_hint: str) -> list[dict]:
    """Parse RSS 2.0 or RSS 1.0/RDF into capture records. Namespace-agnostic."""
    root = ET.fromstring(body)
    records: list[dict] = []
    for item in root.iter():
        if item.tag.split("}")[-1].lower() != "item":
            continue
        title = _text(item, "title")
        link = _text(item, "link")
        if not link:
            # RSS 1.0 / RDF puts the URL in rdf:about on the <item>
            link = item.attrib.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about", "")
        desc = _text(item, "description", "encoded")
        posted = _text(item, "date", "pubdate", "issued")
        if not (title or link):
            continue
        records.append({
            "source": name,
            "title": title,
            "url": link,
            "description": desc,
            "posted": posted,
            "market": market_hint,
        })
    return records


def run_headless_capture(capture_dir: Path, searches: dict) -> list[Path]:
    written: list[Path] = []
    for feed in searches.get("rss", []):
        if not feed.get("enabled", True):
            continue
        name = feed.get("name", "Craigslist")
        records, error = fetch_rss(name, feed["url"], feed.get("market_hint", ""))
        slug = hp.slug(f"{name}-{feed.get('label', feed.get('market_hint',''))}") or "feed"
        out = capture_dir / f"rss-{slug}.json"
        out.write_text(json.dumps(records, indent=2), encoding="utf-8")
        written.append(out)
        status = "blocked" if error else f"{len(records)} items"
        print(f"  rss {name} [{feed.get('label', feed.get('market_hint',''))}]: {status}", file=sys.stderr)
    return written


def clear_capture_json(capture_dir: Path) -> int:
    """Remove old scratch captures before a scheduled kickoff.

    The pipeline treats every ingested capture as "seen on this run". Scheduled
    browser captures therefore need a clean scratch dir at the first kickoff so an
    old ai-*.json cannot keep a stale Facebook/Zillow/Furnished Finder listing alive.
    """
    removed = 0
    for path in capture_dir.glob("*.json"):
        try:
            path.unlink()
            removed += 1
        except OSError as exc:
            print(f"WARNING: could not remove stale capture {path}: {exc}", file=sys.stderr)
    return removed


def print_ai_capture_plan(searches: dict, capture_dir: Path, sources_arg: list[str] | None = None) -> None:
    # Human/conductor guidance goes to stderr so stdout stays clean parseable JSON.
    def out(*args):
        print(*args, file=sys.stderr)

    plan = searches.get("ai_browser", [])
    out("\n================ AI CAPTURE PLAN ================")
    if not plan:
        out("No AI-browser sources configured.")
        return
    out(
        "These sources need a visible/logged-in browser. The CONDUCTOR captures\n"
        "them (Codex: Chrome plugin; Claude: Claude-in-Chrome / Computer Use),\n"
        "writing ONE JSON array per source into the capture dir, then re-runs this\n"
        "script. Capture visible facts only — never bypass CAPTCHA/login/rate limits,\n"
        "never message posters or submit anything.\n"
    )
    out(f"Capture dir: {capture_dir}")
    out("Record schema: see references/sources.md (title,url,city,neighborhood,rent,lease,available,description,posted)\n")
    for i, src in enumerate(plan, 1):
        name = src.get("name", "source")
        dest = capture_dir / f"ai-{hp.slug(name)}.json"
        out(f"{i}. {name}  [{src.get('market_hint','')}]")
        if src.get("search_url"):
            out(f"   open : {src['search_url']}")
        if src.get("cities"):
            out(f"   cities: {', '.join(str(city) for city in src['cities'])}")
        if src.get("centers"):
            centers = ", ".join(
                str(center.get("label") or f"{center.get('latitude')},{center.get('longitude')}")
                for center in src["centers"]
                if isinstance(center, dict)
            )
            if centers:
                out(f"   areas : {centers}")
        if src.get("note"):
            out(f"   note : {src['note']}")
        out(f"   write: {dest}")
    out("\nThen re-run:")
    inputs = " ".join(str(capture_dir / f"ai-{hp.slug(s.get('name','source'))}.json") for s in plan)
    sources_part = ""
    if sources_arg and parse_source_filters(sources_arg) != {"all"}:
        sources_part = " --sources " + " ".join(sources_arg)
    out(f"   python3 {Path(__file__).name}{sources_part} --input {inputs}")
    out("================================================\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Kickoff the Bay Area housing hunt (headless + plan).")
    parser.add_argument("--capture-dir", type=Path, default=DEFAULT_CAPTURE_DIR)
    parser.add_argument("--input", nargs="*", type=Path, default=[], help="Extra capture file(s) to ingest (e.g. AI-produced)")
    parser.add_argument("--source", default="manual")
    parser.add_argument("--sources", nargs="+", default=["all"], help="One or more configured sources to run/plan (default: all). Examples: --sources craigslist zillow facebook, --sources craigslist,zillow,facebook, or --sources apartments.com")
    parser.add_argument("--list-sources", action="store_true", help="Print selectable configured sources/tokens and exit")
    parser.add_argument("--fresh-capture-dir", action="store_true", help="Delete existing *.json files in the capture dir before the kickoff run")
    parser.add_argument("--no-network", action="store_true", help="Skip the headless web/API fetch")
    parser.add_argument("--notion", action="store_true", help="After refreshing, mirror the ledger into Notion (no-op unless NOTION_TOKEN + housing-trackers/notion-config.md are set)")
    parser.add_argument("--plan-only", action="store_true", help="Do not ingest/score; just print the AI capture plan")
    parser.add_argument("--date", default=hp.today_iso())
    parser.add_argument("--stale-days", type=int, default=3)
    parser.add_argument("--retire-days", type=int, default=14)
    args = parser.parse_args()

    capture_dir = args.capture_dir
    capture_dir.mkdir(parents=True, exist_ok=True)
    if args.fresh_capture_dir:
        removed = clear_capture_json(capture_dir)
        print(f"Cleared {removed} old capture file(s) from {capture_dir}", file=sys.stderr)
    searches = load_searches()
    searches, source_filters = filter_searches(searches, args.sources)
    if args.list_sources:
        list_configured_sources(searches)
        return 0
    if "all" not in source_filters:
        counts = selected_source_counts(searches)
        print(
            "Selected sources "
            f"{' '.join(args.sources)!r}: web={counts['web']}, rss={counts['rss']}, "
            f"apis={counts['apis']}, ai_browser={counts['ai_browser']}",
            file=sys.stderr,
        )

    if args.plan_only:
        print_ai_capture_plan(searches, capture_dir, args.sources)
        return 0

    captured: list[Path] = []
    for path in args.input:
        if not path.exists():
            print(f"WARNING: --input not found, skipping: {path}", file=sys.stderr)
            continue
        captured.append(path.resolve())
    if not args.no_network:
        print("Running headless capture (web adapters + configured APIs; optional legacy RSS if configured)...", file=sys.stderr)
        captured.extend(p.resolve() for p in capture_web.run_web_capture(capture_dir, searches))
        captured.extend(p.resolve() for p in run_headless_capture(capture_dir, searches))
        captured.extend(p.resolve() for p in capture_api.run_api_capture(capture_dir, searches))
    # Ingest every capture file present in the dir plus any explicit --input.
    for path in sorted(capture_dir.glob("*.json")):
        if not capture_path_matches(path, source_filters):
            continue
        captured.append(path.resolve())
    # De-dupe by resolved path (so --input X and the dir glob can't double-process),
    # preserve order, keep only existing files.
    seen: set[Path] = set()
    deduped: list[Path] = []
    for path in captured:
        if path not in seen and path.exists():
            seen.add(path)
            deduped.append(path)
    captured = deduped

    summary = hp.run(
        inputs=captured,
        default_source=args.source,
        run_date=args.date,
        stale_days=args.stale_days,
        retire_days=args.retire_days,
    )
    print(json.dumps(summary, indent=2))
    if summary.get("warnings"):
        print("\nWarnings:", file=sys.stderr)
        for w in summary["warnings"]:
            print(f"  - {w}", file=sys.stderr)

    if args.notion:
        print("Mirroring to Notion...", file=sys.stderr)
        import subprocess
        subprocess.run([sys.executable, str(SCRIPT_DIR / "sync_housing_to_notion.py")], check=False)

    print_ai_capture_plan(searches, capture_dir, args.sources)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
