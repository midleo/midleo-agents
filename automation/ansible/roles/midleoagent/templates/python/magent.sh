#!/bin/bash

#script for midleo.CORE agent
#created by V.Vasilev
#https://vasilev.link

set -euo pipefail

cd "$(dirname "$0")" || exit 1
USR="$(whoami)"
HOMEDIR="$(pwd)/config"

if [ ! -f "$HOMEDIR/mwagent.config" ]; then
  echo "no mwagent.config file found"
  exit 1
fi

. "$HOMEDIR/mwagent.config"

export DSPMQ
export DSPMQVER
export AMQSEVT
export RUNMQSC
export ACEUSR
export MQSIPROFILE
export IIBMQSIPROFILE
export PYTHON

usage() {
  "$0"
  exit 1
}

require_arg() {
  if [ -z "${1:-}" ]; then
    usage
  fi
}

require_qmgr() {
  require_arg "${1:-}"
  if [[ ! "$1" =~ ^[A-Za-z0-9._%/-]+$ ]]; then
    echo "Invalid Qmanager"
    exit 1
  fi
}

"$PYTHON" - <<'PY'
import os
from modules.base import configs

cfgdir = os.path.join(os.getcwd(), "config")
os.makedirs(cfgdir, exist_ok=True)

if not os.path.isfile(os.path.join(cfgdir, "cronjobs.json")):
    raise SystemExit("missing config/cronjobs.json")

for path in (
    os.path.join(cfgdir, "certs.json"),
    os.path.join(cfgdir, "conftrack.json"),
    os.path.join(cfgdir, "confavl.json"),
    os.path.join(cfgdir, "confapplstat.json"),
    os.path.join(cfgdir, "confoptadvisor.json"),
    os.path.join(cfgdir, "confactions.json"),
):
    if not os.path.isfile(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("{}\n")

configs.syncCronjobsForConfig("conftrack.json", configs.gettrackData())
configs.syncCronjobsForConfig("confavl.json", configs.getAvlData())
configs.syncCronjobsForConfig("confapplstat.json", configs.getmonData())
configs.syncCronjobsForConfig("confoptadvisor.json", configs.getOptAdvisorData())
PY

case "${1:-}" in
  addcert )
      require_arg "${2:-}"
      "$PYTHON" "runable/addcert.py" "$2"
      ;;
  delcert )
      if [ -z "${2:-}" ]; then
        "$0"
        exit 1
      fi
      "$PYTHON" "runable/delcert.py" "$2"
      ;;
  enableavl )
      require_arg "${2:-}"
      require_arg "${3:-}"
      appsrv="$2"
      appsrvtype="$3"
      shift 3
      mondata="${*:-{}}"
      "$PYTHON" "runable/enableavl.py" "$appsrv" "$appsrvtype" "$mondata"
      ;;
  disableavl )
      require_arg "${2:-}"
      require_arg "${3:-}"
      "$PYTHON" "runable/disableavl.py" "$2" "$3"
      ;;
  stopavl )
      require_arg "${2:-}"
      require_arg "${3:-}"
      require_arg "${4:-}"
      "$PYTHON" "runable/stopavl.py" "$USR" "$2" "$3" "$4"
      ;;
  startavl )
      require_arg "${2:-}"
      require_arg "${3:-}"
      "$PYTHON" "runable/startavl.py" "$USR" "$2" "$3"
      ;;
  addappstat )
      require_arg "${2:-}"
      require_arg "${3:-}"
      require_arg "${4:-}"
      "$PYTHON" "runable/addappstat.py" "$2" "$3" "$4"
      ;;
  addoptadvisor )
      require_arg "${2:-}"
      require_arg "${3:-}"
      require_arg "${4:-}"
      "$PYTHON" "runable/addoptadvisor.py" "$2" "$3" "$4"
      ;;
  addaction )
      if [ -z "${2:-}" ]; then
        "$0"
        exit 1
      fi
      if [ -n "${3:-}" ]; then
        "$PYTHON" "runable/addaction.py" "$2" "$3"
      else
        "$PYTHON" "runable/addaction.py" "$2"
      fi
      ;;
  delappstat )
      require_arg "${2:-}"
      require_arg "${3:-}"
      "$PYTHON" "runable/delappstat.py" "$2" "$3"
      ;;
  deloptadvisor )
      require_arg "${2:-}"
      require_arg "${3:-}"
      "$PYTHON" "runable/deloptadvisor.py" "$2" "$3"
      ;;
  enableoptadvisor )
      "$PYTHON" "runable/optadvisorctl.py" enable "${2:-30}"
      ;;
  disableoptadvisor )
      shift
      "$PYTHON" "runable/optadvisorctl.py" disable "${*:-manual}"
      ;;
  optadvisorstatus )
      "$PYTHON" "runable/optadvisorctl.py" status
      ;;
  rmaction )
      if [ -z "${2:-}" ]; then
        "$0"
        exit 1
      fi
      "$PYTHON" "runable/rmaction.py" "$2"
      ;;
  enabletrackqm )
      require_qmgr "${2:-}"
      sudo -u mqm -i "$RUNMQSC" "$2" <<'MQSC'
ALTER QMGR ACTVTRC(ON)
MQSC
      "$PYTHON" "runable/enabletrackqm.py" "$2"
      ;;
  disabletrackqm )
      require_qmgr "${2:-}"
      sudo -u mqm -i "$RUNMQSC" "$2" <<'MQSC'
ALTER QMGR ACTVTRC(OFF)
MQSC
      "$PYTHON" "runable/disabletrackqm.py" "$2"
      ;;
  maintenance )
      if [ -z "${2:-}" ]; then
        echo "usage: $0 maintenance on|off [comment]"
        exit 1
      fi
      if [ "$2" = "on" ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') ${3:-}" > "$HOMEDIR/maintenance.flag"
      elif [ "$2" = "off" ]; then
        rm -f "$HOMEDIR/maintenance.flag"
      else
        echo "usage: $0 maintenance on|off [comment]"
        exit 1
      fi
      "$PYTHON" "runable/setmaintenance.py" "$2" "${3:-}"
      ;;
  * )
      echo ""
      echo "usage:"
      echo "   -  $0 addcert '{\"tool\":\"keytool\",\"keystore\":\"/var/tmp/key.jks\",\"excluded\":\"alias1,alias2\",\"password\":\"testpass\"}'"
      echo "   -  $0 delcert LABEL_OR_KEYSTORE"
      echo "   -  $0 enableavl APP_SERVER SERVER_TYPE '{\"docker\":\"DOCKER_CONTAINER_NAME\",\"user\":\"USERNAME_FOR_APPLICATION_SERVER_ACCESS\",\"pass\":\"PASSWORD_FOR_APPLICATION_SERVER_ACCESS\"}'"
      echo "   -  $0 enableavl WEBLOGIC_HOST weblogic '{\"conntype\":\"rest\",\"user\":\"USERNAME_FOR_WEBLOGIC_REST\",\"pass\":\"PASSWORD_FOR_WEBLOGIC_REST\",\"ssl\":\"yes\",\"mngmport\":\"9002\",\"appserver\":\"AdminServer\",\"appsrvid\":\"MIDLEO_SERVER_ID\"}'"
      echo "   -  $0 disableavl APP_SERVER SERVER_TYPE"
      echo "   -  $0 stopavl APP_SERVER SERVER_TYPE comment"
      echo "   -  $0 startavl APP_SERVER SERVER_TYPE"
      echo "   -  $0 addappstat SRV_TYPE APPSRV '{\"queues\":\"TEST.*,VVV.*\",\"channels\":\"SDR.*,CHL.*\"}'"
      echo "   -  $0 delappstat SRV_TYPE APPSRV"
      echo "   -  $0 addoptadvisor SRV_TYPE APPSRV '{\"appsrvid\":\"MIDLEO_SERVER_ID\",\"usr\":\"USER\",\"pass\":\"PASS\",\"mngmport\":\"7001\"}'"
      echo "   -  $0 deloptadvisor SRV_TYPE APPSRV"
      echo "   -  $0 enableoptadvisor [days]       # max 30 days, requires per-server optadvisor config"
      echo "   -  $0 disableoptadvisor [reason]"
      echo "   -  $0 optadvisorstatus"
      echo "   -  $0 addaction APP_SERVER_TYPE.ERROR_CODE '{\"script\":\"/opt/midleo/actions/restart.sh\",\"args\":[\"{appserver_type}\",\"{error_code}\"],\"monid\":\"monaction\",\"appsrvid\":\"none\",\"appsrv\":\"tomcat01\",\"message\":\"Action already started recently\"}'"
      echo "   -  $0 addaction '{\"action_key\":\"APP_SERVER_TYPE.ERROR_CODE\",\"script\":\"/opt/midleo/actions/restart.sh\"}'"
      echo "   -  $0 rmaction APP_SERVER_TYPE.ERROR_CODE"
      echo "   -  $0 enabletrackqm QMGR"
      echo "   -  $0 disabletrackqm QMGR"
      echo "   -  $0 maintenance on|off [comment]"
      echo ""
      ;;
esac
