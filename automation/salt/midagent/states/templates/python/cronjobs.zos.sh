#!/bin/sh

# z/OS USS cron runner for midleo.CORE agent.

set -eu

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
MWAGTDIR="$SCRIPT_DIR"

if [ ! -d "$MWAGTDIR/runable" ] || [ ! -d "$MWAGTDIR/config" ]; then
  if [ -d "$SCRIPT_DIR/../runable" ] && [ -d "$SCRIPT_DIR/../config" ]; then
    MWAGTDIR=$(CDPATH= cd "$SCRIPT_DIR/.." && pwd)
  else
    exit 1
  fi
fi

HOMEDIR="$MWAGTDIR/config"
LOCKDIR="$HOMEDIR/.mwagent_cron.lock"
PIDFILE="$LOCKDIR/pid"

mkdir -p "$HOMEDIR"

if mkdir "$LOCKDIR" 2>/dev/null; then
  echo "$$" > "$PIDFILE"
else
  if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE" 2>/dev/null || true)
    if [ -n "${OLD_PID:-}" ] && kill -0 "$OLD_PID" 2>/dev/null; then
      exit 0
    fi
  fi

  rm -rf "$LOCKDIR"
  mkdir "$LOCKDIR"
  echo "$$" > "$PIDFILE"
fi

trap 'rm -rf "$LOCKDIR"' EXIT HUP INT TERM

. "$MWAGTDIR/zos_env.sh"
midleo_load_zos_env

cd "$MWAGTDIR"

exec "$PYTHON" "$MWAGTDIR/runable/run_cronjobs.py"
