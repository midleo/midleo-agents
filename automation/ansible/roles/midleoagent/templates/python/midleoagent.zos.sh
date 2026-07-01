#!/bin/sh

# z/OS USS lifecycle wrapper. Use foreground modes from BPXBATCH started tasks.

set -eu

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
MWAGTDIR="$SCRIPT_DIR"
HOMEDIR="$MWAGTDIR/config"
RUNDIR="$MWAGTDIR/run"
LOGDIR="$MWAGTDIR/logs"

mkdir -p "$RUNDIR" "$LOGDIR"

. "$MWAGTDIR/zos_env.sh"
midleo_load_zos_env

AGENT_PIDFILE="$RUNDIR/midleoagent.pid"
ACTIONS_PIDFILE="$RUNDIR/midleoactions.pid"

run_foreground() {
  name="$1"
  script="$2"
  pidfile="$3"

  cd "$MWAGTDIR"
  "$PYTHON" -u "$script" &
  child_pid=$!
  echo "$child_pid" > "$pidfile"

  trap 'kill -TERM "$child_pid" 2>/dev/null || true; wait "$child_pid" 2>/dev/null || true; rm -f "$pidfile"; exit 0' HUP INT TERM
  set +e
  wait "$child_pid"
  rc=$?
  set -e
  rm -f "$pidfile"
  echo "$name stopped rc=$rc"
  return "$rc"
}

start_one() {
  name="$1"
  script="$2"
  pidfile="$3"
  logfile="$4"

  if [ -f "$pidfile" ]; then
    old_pid=$(cat "$pidfile" 2>/dev/null || true)
    if [ -n "${old_pid:-}" ] && kill -0 "$old_pid" 2>/dev/null; then
      echo "$name already running pid=$old_pid"
      return 0
    fi
  fi

  cd "$MWAGTDIR"
  nohup "$PYTHON" -u "$script" >> "$logfile" 2>&1 &
  echo "$!" > "$pidfile"
  echo "$name started pid=$(cat "$pidfile")"
}

stop_one() {
  name="$1"
  pidfile="$2"

  if [ ! -f "$pidfile" ]; then
    echo "$name not running"
    return 0
  fi

  pid=$(cat "$pidfile" 2>/dev/null || true)
  if [ -z "${pid:-}" ]; then
    rm -f "$pidfile"
    echo "$name not running"
    return 0
  fi

  if kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid" 2>/dev/null || true
    i=0
    while kill -0 "$pid" 2>/dev/null && [ "$i" -lt 20 ]; do
      sleep 1
      i=$((i + 1))
    done
  fi

  rm -f "$pidfile"
  echo "$name stopped"
}

status_one() {
  name="$1"
  pidfile="$2"

  if [ -f "$pidfile" ]; then
    pid=$(cat "$pidfile" 2>/dev/null || true)
    if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
      echo "$name running pid=$pid"
      return 0
    fi
  fi

  echo "$name stopped"
  return 1
}

case "${1:-status}" in
  agent-foreground|foreground)
    run_foreground midleoagent "$MWAGTDIR/midleo_client.py" "$AGENT_PIDFILE"
    ;;
  actions-foreground)
    run_foreground midleoactions "$MWAGTDIR/midleo_actions.py" "$ACTIONS_PIDFILE"
    ;;
  agent-start)
    start_one midleoagent "$MWAGTDIR/midleo_client.py" "$AGENT_PIDFILE" "$LOGDIR/midleoagent.out"
    ;;
  actions-start)
    start_one midleoactions "$MWAGTDIR/midleo_actions.py" "$ACTIONS_PIDFILE" "$LOGDIR/midleoactions.out"
    ;;
  start)
    start_one midleoagent "$MWAGTDIR/midleo_client.py" "$AGENT_PIDFILE" "$LOGDIR/midleoagent.out"
    start_one midleoactions "$MWAGTDIR/midleo_actions.py" "$ACTIONS_PIDFILE" "$LOGDIR/midleoactions.out"
    ;;
  agent-stop)
    stop_one midleoagent "$AGENT_PIDFILE"
    ;;
  actions-stop)
    stop_one midleoactions "$ACTIONS_PIDFILE"
    ;;
  stop)
    stop_one midleoactions "$ACTIONS_PIDFILE"
    stop_one midleoagent "$AGENT_PIDFILE"
    ;;
  restart)
    "$0" stop
    "$0" start
    ;;
  agent-status)
    status_one midleoagent "$AGENT_PIDFILE"
    ;;
  actions-status)
    status_one midleoactions "$ACTIONS_PIDFILE"
    ;;
  status)
    rc=0
    status_one midleoagent "$AGENT_PIDFILE" || rc=1
    status_one midleoactions "$ACTIONS_PIDFILE" || rc=1
    exit "$rc"
    ;;
  *)
    echo "usage: $0 start|stop|restart|status|agent-foreground|actions-foreground"
    exit 1
    ;;
esac
