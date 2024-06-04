#!/bin/bash

#script for midleo.CORE agent
#created by V.Vasilev
#https://vasilev.link
cd $(dirname $0)
USR=`whoami`

addcert(){
/usr/bin/python3 << EOF
import base64,platform,json,re,uuid,time,subprocess,socket,sys,os
from datetime import datetime
from modules import makerequest,decrypt,classes,configs

if platform.system()=="Linux":
   from modules import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules import win_utils
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
/usr/bin/python3 << EOF
import base64,platform,json,re,uuid,time,subprocess,socket,sys,os
from datetime import datetime
from modules import makerequest,classes,configs

if platform.system()=="Linux":
   from modules import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules import win_utils
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
/usr/bin/python3 << EOF
import base64,platform,json,re,uuid,time,subprocess,socket,sys,os
from datetime import datetime
from modules import makerequest,classes,configs

if platform.system()=="Linux":
   from modules import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules import win_utils
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
/usr/bin/python3 << EOF
import base64,platform,json,re,uuid,time,subprocess,socket,sys,os
from datetime import datetime
from modules import makerequest,classes,configs

if platform.system()=="Linux":
   from modules import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules import win_utils
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
/usr/bin/python3 << EOF
import base64,platform,json,re,uuid,time,sys,os
from datetime import datetime
from modules import classes,configs

if platform.system()=="Linux":
   from modules import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules import win_utils
else:
   exit()
USR="$USR"
APPSRV="$1"
APPSRVTYPE="$2"

def createAvlJson():
   try:
      avl_data = configs.getAvlData()
   except Exception as err:
      avl_data = {}
   
   avl_data[APPSRV] = {
     "type": APPSRVTYPE,
     "enabled": "yes"
   }

   with open(os.getcwd()+"/config/confavl.json", 'w+') as avl_file:
      json.dump(avl_data, avl_file)
   print("Availability check for "+APPSRV+" have been enabled")
    
if __name__ == "__main__":
   createAvlJson()

EOF
}

disableavl(){
/usr/bin/python3 << EOF
import base64,platform,json,re,uuid,time,sys,os
from datetime import datetime
from modules import classes,configs

if platform.system()=="Linux":
   from modules import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules import win_utils
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
/usr/bin/python3 << EOF
import base64,platform,json,re,uuid,time,sys,os
from datetime import datetime
from modules import classes,configs

if platform.system()=="Linux":
   from modules import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules import win_utils
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
/usr/bin/python3 << EOF
import base64,platform,json,re,uuid,time,sys,os
from datetime import datetime
from modules import classes,configs

if platform.system()=="Linux":
   from modules import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules import win_utils
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
      enableavl $2 $3
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
   * )
      echo ""
      echo "usage:"
      echo "   -  $0 addcert"
      echo "   -  $0 delcert LABEL"
      echo "   -  $0 addstat"
      echo "   -  $0 delstat FILE_PATH"
      echo "   -  $0 enableavl APP_SERVER SERVER_TYPE"
      echo "   -  $0 disableavl APP_SERVER"
      echo "   -  $0 stopavl APP_SERVER comment"
      echo "   -  $0 startavl APP_SERVER"
   esac