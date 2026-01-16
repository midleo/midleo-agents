#!/bin/bash

#script for midleo.CORE agent
#created by V.Vasilev
#https://vasilev.link

set -euo pipefail

LOCKDIR="/tmp/mwagent.lock"
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  exit 0
fi
trap 'rmdir "$LOCKDIR"' EXIT

cd "$(dirname "$0")" || exit 1

MWAGTDIR="$(pwd)"
HOMEDIR="$MWAGTDIR/config"

mkdir -p "$HOMEDIR"

if [[ ! -f "$HOMEDIR/mwagent.config" ]]; then
  exit 1
fi

. "$HOMEDIR/mwagent.config"

: "${PYTHON:?PYTHON not set}"

export DSPMQ
export DSPMQVER
export AMQSEVT
export RUNMQSC
export ACEUSR
export MQSIPROFILE
export IIBMQSIPROFILE
export MWAGTDIR

YM=$(date '+%Y-%m')
WD=$(date '+%d')
HOUR=$(date '+%H%M')
CM=$(date '+%M')

LRFILE="$HOMEDIR/nextrun.txt"
NOW_TS=$(date '+%s')
TST="$NOW_TS"

if [[ -f "$LRFILE" ]]; then
  read -r T < "$LRFILE" || true
  [[ -n "${T:-}" ]] && TST="$T"
fi

if [[ "${1:-}" == "help" ]]; then
  echo "Cronjobs for MWAdmin"
  echo "Used for background processes"
  exit 0
fi

if [[ -f "$HOMEDIR/confapplstat.json" ]]; then
  if [[ "$CM" == "00" || "$CM" == "30" ]]; then
    "$PYTHON" runable/resetapplstat.py
  else
    "$PYTHON" runable/getapplstat.py
  fi
fi

if [[ -f "$HOMEDIR/conftrack.json" ]]; then
  "$PYTHON" runable/runmqtracker.py
fi

if [[ -f "$HOMEDIR/confavl.json" ]]; then
  if [[ "$HOUR" == "2359" ]]; then
    "$PYTHON" runable/resetappavl.py "$YM" "$WD"
  else
    "$PYTHON" runable/runappavllin.py
  fi

  if [[ -n "${AMQSEVT:-}" && -x "$AMQSEVT" ]]; then
    "$PYTHON" runable/runmqevents.py || true
  fi
fi

if [[ "$TST" -le "$NOW_TS" ]]; then
  "$PYTHON" runable/getsrvdata.py
fi

"$PYTHON" runable/getextmonchecks.py
