#!/bin/bash

#script for midleo.CORE agent
#created by V.Vasilev
#https://vasilev.link

set -euo pipefail

SCRIPT_PATH="$(readlink -f "$0")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
MWAGTDIR="$SCRIPT_DIR"

if [ -d "$MWAGTDIR/runable" ] && [ -d "$MWAGTDIR/config" ]; then
  :
elif [ -d "$SCRIPT_DIR/../runable" ] && [ -d "$SCRIPT_DIR/../config" ]; then
  MWAGTDIR="$(readlink -f "$SCRIPT_DIR/..")"
else
  exit 1
fi

HOMEDIR="$MWAGTDIR/config"
LOCKDIR="$HOMEDIR/.mwagent_cron.lock"
PIDFILE="$LOCKDIR/pid"

mkdir -p "$HOMEDIR"

if mkdir "$LOCKDIR" 2>/dev/null; then
  echo "$$" > "$PIDFILE"
else
  if [ -f "$PIDFILE" ]; then
    OLD_PID="$(cat "$PIDFILE" 2>/dev/null || true)"
    if [ -n "${OLD_PID:-}" ] && kill -0 "$OLD_PID" 2>/dev/null; then
      exit 0
    fi
  fi

  rm -rf -- "$LOCKDIR"
  mkdir "$LOCKDIR"
  echo "$$" > "$PIDFILE"
fi

trap 'rm -rf -- "$LOCKDIR"' EXIT

if [ ! -f "$HOMEDIR/mwagent.config" ]; then
  exit 1
fi

set -a
# shellcheck disable=SC1091
. "$HOMEDIR/mwagent.config"
set +a
export -n INTTOKEN

: "${PYTHON:?PYTHON not set}"

cd "$MWAGTDIR"
export MWAGTDIR

exec "$PYTHON" "$MWAGTDIR/runable/run_cronjobs.py"
