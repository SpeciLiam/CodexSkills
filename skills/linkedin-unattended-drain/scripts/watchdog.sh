#!/bin/bash
# Watchdog for linkedin-unattended-drain.
#
# Responsibilities (deterministic — never left to model memory):
#   - keep the Mac awake (caffeinate) for its own lifetime
#   - guard RAM: write/remove a flag file the conductor checks each checkpoint
#   - detect a dead/stalled conductor session and notify Liam
#   - reconcile tracker -> SQLite mirror + visualizer cache when the tracker changes
#   - on terminal state: final reconcile, digest, notification, exit
#
# Usage: watchdog.sh [--interval SEC] [--stale-min MIN] [--ram-floor PCT] [--once]
set -u

# DRAIN_ROOT / DRAIN_STATE_PREFIX are overridable for dry-runs only.
ROOT="${DRAIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
# The ~/.claude/skills mirror resolves ROOT to ~/.claude; fall back to the repo.
if [[ -z "${DRAIN_ROOT:-}" && ! -d "$ROOT/application-trackers" ]]; then
  ROOT="/Users/liamvan/Documents/Repos/CodexSkills"
fi
PREFIX="${DRAIN_STATE_PREFIX:-/tmp/linkedin_unattended_drain}"
STATE="${PREFIX}_state.json"
LOCK="${PREFIX}_worker.lock"
RAM_FLAG="${PREFIX}_ram_warning"
LOG="${PREFIX}_watchdog.log"
PIDFILE="${PREFIX}_watchdog.pid"

INTERVAL=120
STALE_MIN=30
RAM_FLOOR=12
ONCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --interval) INTERVAL="$2"; shift 2 ;;
    --stale-min) STALE_MIN="$2"; shift 2 ;;
    --ram-floor) RAM_FLOOR="$2"; shift 2 ;;
    --once) ONCE=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG"; }

notify() { # notify "title" "body"
  osascript -e "display notification \"${2//\"/}\" with title \"${1//\"/}\" sound name \"Glass\"" 2>/dev/null
  log "NOTIFY: $1 — $2"
}

# --- single watchdog instance ---
if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "watchdog already running (pid $(cat "$PIDFILE"))" >&2
  exit 1
fi
echo $$ > "$PIDFILE"

cleanup() {
  [[ -n "${CAFF_PID:-}" ]] && kill "$CAFF_PID" 2>/dev/null
  rm -f "$PIDFILE"
}
trap cleanup EXIT INT TERM

# Keep display-off-but-awake for the life of this watchdog only.
caffeinate -dims -w $$ &
CAFF_PID=$!

log "watchdog start pid=$$ interval=${INTERVAL}s stale=${STALE_MIN}m ram_floor=${RAM_FLOOR}% root=$ROOT"

free_pct() {
  memory_pressure 2>/dev/null | awk -F': ' '/System-wide memory free percentage/ {gsub(/%/,"",$2); print int($2); found=1} END {if (!found) print -1}'
}

state_query() { # state_query <python expr over dict s> ; prints result or ""
  python3 - "$STATE" "$1" <<'PY' 2>/dev/null
import json, sys
try:
    s = json.load(open(sys.argv[1]))
    print(eval(sys.argv[2], {"s": s}))
except Exception:
    pass
PY
}

TERMINAL_STATES="('submitted','manual','archived','already_applied','already_submitted','duplicate')"

reconcile() {
  (cd "$ROOT" && python3 scripts/mirror_to_sqlite.py >> "$LOG" 2>&1 \
    && python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py >> "$LOG" 2>&1) \
    && log "reconcile ok" || log "reconcile FAILED (see above)"
}

digest() {
  python3 - "$STATE" <<'PY' 2>/dev/null
import json, sys, collections
s = json.load(open(sys.argv[1]))
counts = collections.Counter(i.get("state", "?") for i in s.get("items", []))
print("DIGEST items=%d %s" % (sum(counts.values()), dict(sorted(counts.items()))))
print("DIGEST saturation=%r stop=%s" % (
    s.get("search", {}).get("saturationReason", ""),
    s.get("search", {}).get("stopRequested", False)))
manual = [i for i in s.get("items", []) if i.get("state") == "manual"]
for i in manual:
    print("DIGEST manual: %s — %s | %s" % (i.get("company"), i.get("role"), (i.get("blocker") or "")[:140]))
PY
}

TRACKER="$ROOT/application-trackers/applications.md"
last_tracker_sig=""
stale_notified=0
ram_strikes=0

while :; do
  # 1) Wait for kickoff if state doesn't exist yet.
  if [[ ! -f "$STATE" ]]; then
    log "waiting for state file"
    [[ $ONCE -eq 1 ]] && exit 0
    sleep "$INTERVAL"; continue
  fi

  # 2) RAM guard.
  pct=$(free_pct)
  if [[ "$pct" -ge 0 && "$pct" -lt "$RAM_FLOOR" ]]; then
    ram_strikes=$((ram_strikes + 1))
    if [[ ! -f "$RAM_FLAG" ]]; then
      date -u +%Y-%m-%dT%H:%M:%SZ > "$RAM_FLAG"
      notify "Drain: low memory" "Free ${pct}% < floor ${RAM_FLOOR}% — conductor will shed tabs"
    fi
    log "ram low: free=${pct}% strikes=${ram_strikes}"
  else
    [[ -f "$RAM_FLAG" ]] && { rm -f "$RAM_FLAG"; log "ram recovered: free=${pct}%"; }
    ram_strikes=0
  fi

  # 3) Reconcile when the tracker changed.
  if [[ -f "$TRACKER" ]]; then
    sig=$(stat -f '%m %z' "$TRACKER" 2>/dev/null)
    if [[ -n "$sig" && "$sig" != "$last_tracker_sig" ]]; then
      [[ -n "$last_tracker_sig" ]] && reconcile
      last_tracker_sig="$sig"
    fi
  fi

  # 4) Terminal-state detection.
  stop=$(state_query 's.get("search",{}).get("stopRequested", False)')
  maxjobs=$(state_query 'int(s.get("runPolicy",{}).get("maxJobs") or 0)')
  done_count=$(state_query "sum(1 for i in s.get('items',[]) if i.get('state') in $TERMINAL_STATES)")
  reason=$(state_query 's.get("search",{}).get("saturationReason","")')
  if [[ "$stop" == "True" || ( -n "$maxjobs" && "$maxjobs" -gt 0 && -n "$done_count" && "$done_count" -ge "$maxjobs" ) ]]; then
    log "terminal state detected (stop=$stop done=$done_count/$maxjobs reason=$reason)"
    reconcile
    digest >> "$LOG"
    submitted=$(state_query "sum(1 for i in s.get('items',[]) if i.get('state')=='submitted')")
    manual=$(state_query "sum(1 for i in s.get('items',[]) if i.get('state')=='manual')")
    if [[ "$reason" == SYSTEMIC:* ]]; then
      notify "Drain STOPPED (systemic)" "$reason"
    else
      notify "Drain complete" "submitted=${submitted:-?} manual=${manual:-?} done=${done_count}. Digest in watchdog log."
    fi
    exit 0
  fi

  # 5) Stalled-session detection (no state write for STALE_MIN while non-terminal).
  state_age_min=$(( ( $(date +%s) - $(stat -f '%m' "$STATE" 2>/dev/null || date +%s) ) / 60 ))
  lock_pid=$(python3 -c "import json;print(json.load(open('$LOCK')).get('pid') or '')" 2>/dev/null)
  lock_alive=0
  [[ "$lock_pid" =~ ^[0-9]+$ ]] && kill -0 "$lock_pid" 2>/dev/null && lock_alive=1
  if [[ "$state_age_min" -ge "$STALE_MIN" && "$lock_alive" -eq 0 ]]; then
    if [[ "$stale_notified" -eq 0 ]]; then
      notify "Drain looks stalled" "No state write for ${state_age_min}m and no live worker. Resume: build_run_state.py --resume + \$linkedin-unattended-drain"
      stale_notified=1
    fi
    log "stalled: age=${state_age_min}m lock_alive=${lock_alive}"
  elif [[ "$state_age_min" -lt "$STALE_MIN" ]]; then
    stale_notified=0
  fi

  [[ $ONCE -eq 1 ]] && exit 0
  sleep "$INTERVAL"
done
