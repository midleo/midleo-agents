#!/bin/bash

#script for midleo.CORE agent
#created by V.Vasilev
#https://vasilev.link

cd $(dirname $0)
USR=`whoami`

HOMEDIR=$(pwd)"/config"
DSPMQVER=/opt/mqm/bin/dspmqver
DSPMQ=/opt/mqm/bin/dspmq
RUNMQSC=/opt/mqm/bin/runmqsc
AMQSEVT=/opt/mqm/bin/amqsevt
ACEUSR=mqbrk
MQSIPROFILE=/opt/ibm/ace/server/bin/mqsiprofile
PYTHON=/usr/bin/python3

export DSPMQ
export DSPMQVER
export AMQSEVT
export RUNMQSC
export ACEUSR
export MQSIPROFILE

YM=$(date '+%Y-%m')
WD=$(date '+%d')
HOUR=$(date '+%H%M')

addcert(){
$PYTHON << EOF
import base64,platform,json,re,uuid,time,subprocess,socket,sys,os
from datetime import datetime
from modules.base import makerequest,decrypt,classes,configs

if platform.system()=="Linux":
   from modules.base import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules.base import win_utils
else:
   exit()

CERT="$1"

def createCertJson():
   config_data = configs.getcfgData()
   uid = config_data['uid']

   if not uid:
      pass

   try:
      cert_data = configs.getcertData()
   except Exception as err:

      cert_data = {}

   cert_data[CERT.split("#")[2]] = {
      "command": CERT.split("#")[0],
      "cfile": CERT.split("#")[1],
      "clabel": CERT.split("#")[2],
      "cpass": decrypt.encrypt(CERT.split("#")[3],uid+uid+uid+uid)
   }

   with open(os.getcwd()+"/config/certs.json", 'w+') as cert_file:
      json.dump(cert_data, cert_file)
   print(CERT.split("#")[2]+" configuration added")
    
if __name__ == "__main__":
   createCertJson()
EOF
}

delcert(){
$PYTHON << EOF
import base64,platform,json,re,uuid,time,subprocess,socket,sys,os
from datetime import datetime
from modules.base import makerequest,classes,configs

if platform.system()=="Linux":
   from modules.base import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules.base import win_utils
else:
   exit()

CERT="$1"

try:
   cert_data = configs.getcertData()
except Exception as err:
   print("No such configuration file - config/certs.json")
cert_data.pop(CERT, None)
with open(os.getcwd()+"/config/certs.json", 'w+') as cert_file:
   json.dump(cert_data, cert_file)
print(CERT+" configuration deleted")
EOF
}

addstat(){
$PYTHON << EOF
import base64,platform,json,re,uuid,time,subprocess,socket,sys,os
from datetime import datetime
from modules.base import makerequest,classes,configs

if platform.system()=="Linux":
   from modules.base import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules.base import win_utils
else:
   exit()

STATCONF="$1"

def createStatJson():
   config_data = configs.getcfgData()
   uid = config_data['uid']

   if not uid:
      pass

   try:
      stat_data = configs.getstatData()
   except Exception as err:

      stat_data = {}

   stat_data[STATCONF.split("#")[0]] = {
      "file": STATCONF.split("#")[0],
      "type": STATCONF.split("#")[1],
      "function": STATCONF.split("#")[1]+STATCONF.split("#")[2],
      "line": STATCONF.split("#")[3] if STATCONF.split("#")[3]!="all" else "",
      "clean": False if STATCONF.split("#")[4]=="off" else True
   }

   with open(os.getcwd()+"/config/statlist.json", 'w+') as stat_file:
      json.dump(stat_data, stat_file)
   print(STATCONF.split("#")[2]+" configuration added")
    
if __name__ == "__main__":
   createStatJson()
EOF
}

delstat(){
$PYTHON << EOF
import base64,platform,json,re,uuid,time,subprocess,socket,sys,os
from datetime import datetime
from modules.base import makerequest,classes,configs

if platform.system()=="Linux":
   from modules.base import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules.base import win_utils
else:
   exit()

STATCONF="$1"

try:
   stat_data = configs.getstatData()
except Exception as err:
   print("No such configuration file - config/statlist.json")
stat_data.pop(STATCONF, None)
with open(os.getcwd()+"/config/statlist.json", 'w+') as stat_file:
   json.dump(stat_data, stat_file)
print(STATCONF+" configuration deleted")
EOF
}

enableavl(){
$PYTHON << EOF
import base64,platform,json,re,uuid,time,sys,os
from datetime import datetime
from modules.base import classes,configs

if platform.system()=="Linux":
   from modules.base import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules.base import win_utils
else:
   exit()
USR="$USR"
APPSRV="$1"
APPSRVTYPE="$2"
DOCKERCONT="$3"

def createAvlJson():
   try:
      avl_data = configs.getAvlData()
   except Exception as err:
      avl_data = {}
   
   avl_data[APPSRV] = {
     "type": APPSRVTYPE,
     "enabled": "yes",
     "monid": "monapplavl",
     "dockercont": DOCKERCONT
   }

   with open(os.getcwd()+"/config/confavl.json", 'w+') as avl_file:
      json.dump(avl_data, avl_file)
   print("Availability check for "+APPSRV+" have been enabled")
    
if __name__ == "__main__":
   createAvlJson()

EOF
}

disableavl(){
$PYTHON << EOF
import base64,platform,json,re,uuid,time,sys,os
from datetime import datetime
from modules.base import classes,configs

if platform.system()=="Linux":
   from modules.base import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules.base import win_utils
else:
   exit()

USR="$USR"
APPSRV="$1"

try:
   avl_data = configs.getAvlData()
except Exception as err:
   print("No such configuration file - config/confavl.json")
avl_data.pop(APPSRV, None)
with open(os.getcwd()+"/config/confavl.json", 'w+') as avl_file:
   json.dump(avl_data, avl_file)
print("Availability check for "+APPSRV+" have been disabled")
    
EOF
}

stopavl(){
$PYTHON << EOF
import base64,platform,json,re,uuid,time,sys,os
from datetime import datetime
from modules.base import classes,configs

if platform.system()=="Linux":
   from modules.base import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules.base import win_utils
else:
   exit()

USR="$USR"
APPSRV="$1"
COMMENT="$2"

try:
   avl_data = configs.getAvlData()
except Exception as err:
   print("No such configuration file - config/confavl.json")
try:
   avl_data[APPSRV]["enabled"]="no"
   with open(os.getcwd()+"/config/confavl.json", 'w+') as avl_file:
      json.dump(avl_data, avl_file)
   classes.WriteData("stopped,"+USR+","+COMMENT,"avl_"+APPSRV+".csv")
   print("Availability check for "+APPSRV+" have been stopped")
except Exception as err:
   print("No such availability for:"+APPSRV)

EOF
}

startavl(){
$PYTHON << EOF
import base64,platform,json,re,uuid,time,sys,os
from datetime import datetime
from modules.base import classes,configs

if platform.system()=="Linux":
   from modules.base import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules.base import win_utils
else:
   exit()

USR="$USR"
APPSRV="$1"

try:
   avl_data = configs.getAvlData()
except Exception as err:
   print("No such configuration file - config/confavl.json")
try:
   avl_data[APPSRV]["enabled"]="yes"
   with open(os.getcwd()+"/config/confavl.json", 'w+') as avl_file:
      json.dump(avl_data, avl_file)
   classes.WriteData("started,"+USR,"avl_"+APPSRV+".csv")
   print("Availability check for "+APPSRV+" have been started")
except Exception as err:
   print("No such availability for:"+APPSRV)

EOF
}

enabletrackqm (){
$PYTHON << EOF
import base64,platform,json,re,uuid,time,subprocess,socket,sys,os
from datetime import datetime
from modules.base import makerequest,classes,configs

if platform.system()=="Linux":
   from modules.base import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules.base import win_utils
else:
   exit()

QMGR="$1"

def createTrackJson():
   try:
      track_data = configs.gettrackData()
   except Exception as err:
      track_data = {}

   track_data[QMGR] = {
    "type": "enabled"
   }

   with open(os.getcwd()+"/config/conftrack.json", 'w+') as track_file:
      json.dump(track_data, track_file)
   print(QMGR+" have been added")
    
if __name__ == "__main__":
   createTrackJson()

EOF
}

disabletrackqm (){
$PYTHON << EOF
import base64,platform,json,re,uuid,time,subprocess,socket,sys,os
from datetime import datetime
from modules.base import makerequest,classes,configs

if platform.system()=="Linux":
   from modules.base import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules.base import win_utils
else:
   exit()

QMGR="$1"

try:
   track_data = configs.gettrackData()
except Exception as err:
   print("No such configuration file - config/conftrack.json")
track_data.pop(QMGR, None)
with open(os.getcwd()+"/config/conftrack.json", 'w+') as track_file:
   json.dump(track_data, track_file)
print(QMGR+" configuration deleted")
EOF
}

addappstat(){
$PYTHON << EOF
import base64,platform,json,re,uuid,time,subprocess,socket,sys,os
from datetime import datetime
from modules.base import makerequest,classes,configs

if platform.system()=="Linux":
   from modules.base import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules.base import win_utils
else:
   exit()

SRVTYPE="$1"
APPSRV="$2"
STDATA='$3'

def createMonJson():
   try:
      mon_data = configs.getmonData()
   except Exception as err:
      mon_data = {}
   try:
      STJSDATA=json.loads(STDATA)
   except Exception as err:
      STJSDATA={}
   try:
     for k,item in STJSDATA.items():
         mon_data[SRVTYPE][APPSRV][k] = item
   except Exception as err: 
     try:
        mon_data[SRVTYPE][APPSRV] = {}
     except Exception as err:
        mon_data[SRVTYPE] = {}
        mon_data[SRVTYPE][APPSRV] = {}
     for k,item in STJSDATA.items():
         mon_data[SRVTYPE][APPSRV][k] = item

   with open(os.getcwd()+"/config/confapplstat.json", 'w+') as mon_file:
      json.dump(mon_data, mon_file)
   print(APPSRV+" of type "+SRVTYPE+" have been added")
    
if __name__ == "__main__":
   createMonJson()

EOF
}

delappstat(){
$PYTHON << EOF
import base64,platform,json,re,uuid,time,subprocess,socket,sys,os
from datetime import datetime
from modules.base import makerequest,classes,configs

if platform.system()=="Linux":
   from modules.base import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules.base import win_utils
else:
   exit()

SRVTYPE="$1"
APPSRV="$2"

try:
   mon_data = configs.getmonData()
except Exception as err:
   print("No such configuration file - config/confapplstat.json")
mon_data[SRVTYPE].pop(APPSRV, None)
with open(os.getcwd()+"/config/confapplstat.json", 'w+') as mon_file:
   json.dump(mon_data, mon_file)
print(APPSRV+" configuration deleted")
EOF
}

case "$1" in
	addcert )
      read -p "Tool (keytool or runmqakm):" -e TOOL
      read -p "keystore (ex /var/tmp/key.jks):" -e KEYSTORE
      read -p "Label (ex democert):" -e LABEL
      read -p "Password:" -s -e PWD
      addcert "${TOOL}#${KEYSTORE}#${LABEL}#${PWD}"
      ;;
   addstat )
      read -p "File with statistics:" -e FILE
      read -p "Type (ibmace|ibmmq):" -e TYPE
      read -p "Statistics (JVM|ODBC):" -e STATTYPE
      read -p "Only line (summary|all):" -e LINE
      read -p "Truncate (on|off):" -e TRUNC
      addstat "${FILE}#${TYPE}#${STATTYPE}#${LINE}#${TRUNC}"
      ;;
   delcert )
      if [ -z "$2" ]
      then
        $0
        exit 1
      fi
      delcert $2
      ;;
   delstat )
      if [ -z "$2" ]
      then
        $0
        exit 1
      fi
      delstat $2
      ;;
   enableavl )
      if [ -z "$2" ]
      then
        $0
        exit 1
      fi
      enableavl $2 $3 $4
      ;;
   disableavl )
      if [ -z "$2" ]
      then
        $0
        exit 1
      fi
      disableavl $2
      ;;
   stopavl )
      if [ -z "$3" ]
      then
        $0
        exit 1
      fi
      stopavl $2 "${3}"
      ;;
   startavl )
      if [ -z "$2" ]
      then
        $0
        exit 1
      fi
      startavl $2
      ;;
   addappstat )
      addappstat $2 $3 $4
      ;;
   delappstat )
      if [ -z "$2" ]
      then
        $0
        exit 1
      fi
      delappstat $2 $3
      ;;
   enabletrackqm )
      if [ -z "$2" ]
      then
        echo "Empty Qmanager"
        exit 1
      fi
      sudo su - mqm -c "echo 'ALTER QMGR ACTVTRC(ON)' | $RUNMQSC $2"
      enabletrackqm $2
      ;;
   disabletrackqm )
      if [ -z "$2" ]
      then
        echo "Empty Qmanager"
        exit 1
      fi
      sudo su - mqm -c "echo 'ALTER QMGR ACTVTRC(OFF)' | $RUNMQSC $2"
      disabletrackqm $2
      ;;
   * )
      echo ""
      echo "usage:"
      echo "   -  $0 addcert"
      echo "   -  $0 delcert LABEL"
      echo "   -  $0 addstat"
      echo "   -  $0 delstat FILE_PATH"
      echo "   -  $0 enableavl APP_SERVER SERVER_TYPE DOCKER_CONTAINER(In case it is working on Docker)"
      echo "   -  $0 disableavl APP_SERVER"
      echo "   -  $0 stopavl APP_SERVER comment"
      echo "   -  $0 startavl APP_SERVER"
      echo "   -  $0 addappstat SRV_TYPE APPSRV '{\"queues\":\"TEST.*,VVV.*\",\"channels\":\"SDR.*,CHL.*\"}'"
      echo "   -  $0 delappstat SRV_TYPE APPSRV"
      echo "   -  $0 enabletrackqm QMGR # Transfer the mqat.ini file to /var/mqm/qmgr/QMGR/ folder"
      echo "   -  $0 disabletrackqm QMGR"
      echo ""
      echo "Parameters:"
      echo "   -  TYPE_OF_MON: QAGE - monitor queue age, QFULL - monitor percentage of maxdepth/curdepth"
      echo "   -  THRESHOLD: threshold in percent for QFULL/seconds for QAGE (more than this value will be taken in the report)"
      
   esac