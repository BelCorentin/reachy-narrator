#!/usr/bin/env bash
# Launch the live narrator against the Reachy Mini camera.
# Usage: ./run.sh [--interval N] [--source webcam|dir:<path>] [--recap] [--max-frames N]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$ROOT/.venv/bin/python"

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "ANTHROPIC_API_KEY is not set — export it first." >&2
  exit 1
fi

# Robot preflight only when using the robot source (the default).
NEEDS_ROBOT=1
for arg in "$@"; do
  case "$arg" in webcam|dir:*|--source=webcam|--source=dir:*|--recap) NEEDS_ROBOT=0 ;; esac
done

if [[ "$NEEDS_ROBOT" == 1 ]]; then
  ROBOT_HOST="${REACHY_HOST:-$(getent hosts reachy-mini.local | awk '{print $1; exit}')}"
  if [[ -z "$ROBOT_HOST" ]]; then
    echo "Cannot resolve reachy-mini.local — is the robot on and on the same wifi?" >&2
    echo "(Set REACHY_HOST=<ip> to skip mDNS, or use --source webcam / --source dir:<path>.)" >&2
    exit 1
  fi
  # Daemon 1.8.3 reports its hotspot IP as wlan_ip → SDK dials WebRTC signalling
  # on an unroutable address. Force the real one.
  export REACHY_SIGNALLING_HOST="${REACHY_SIGNALLING_HOST:-$ROBOT_HOST}"
  # Preflight: the signalling server (:8443) only runs after media/acquire.
  curl -s -m5 -X POST "http://$ROBOT_HOST:8000/api/media/acquire" >/dev/null || true
  echo "Robot: $ROBOT_HOST"
fi

mkdir -p "$ROOT/logs"
LOG="$ROOT/logs/run-$(date +%F-%H%M%S).log"
ln -sf "$(basename "$LOG")" "$ROOT/logs/latest.log"
echo "Log: $LOG"

"$PY" -m narrator.main "$@" 2>&1 | tee "$LOG"
