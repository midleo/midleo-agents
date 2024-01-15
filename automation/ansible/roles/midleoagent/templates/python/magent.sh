#!/bin/bash

#script for midleo.CORE agent
#created by V.Vasilev
#https://vasilev.link

addcert(){
/usr/bin/python3 << EOF
import base64,platform,json,re,uuid,time,subprocess,socket,sys,os
from datetime import datetime
from modules import makerequest,decrypt,classes,certcheck

if platform.system()=="Linux":
   from modules import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules import win_utils
else:
   exit()

CERT="$1"

def getcfgData():
   with open(os.getcwd()+"/config/agentConfig.json", 'r') as config_file:
      data=json.load(config_file)
      return data

def getcertData():
   with open(os.getcwd()+"/config/certs.json", 'r') as cert_file:
      cert_data=json.load(cert_file)
      return cert_data

def createCertJson():
   config_data = getcfgData()
   uid = config_data['uid']

   if not uid:
      pass

   try:
      cert_data = getcertData()
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
    
def main():
   createCertJson()

if __name__ == "__main__":
   main()

EOF
}

delcert(){
/usr/bin/python3 << EOF
import base64,platform,json,re,uuid,time,subprocess,socket,sys,os
from datetime import datetime
from modules import makerequest,decrypt,classes,certcheck

if platform.system()=="Linux":
   from modules import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules import win_utils
else:
   exit()

CERT="$1"

def getcertData():
   with open(os.getcwd()+"/config/certs.json", 'r') as cert_file:
      cert_data=json.load(cert_file)
      return cert_data

try:
   cert_data = getcertData()
except Exception as err:
   print("No such configuration file - config/certs.json")
cert_data.pop(CERT, None)
with open(os.getcwd()+"/config/certs.json", 'w+') as cert_file:
   json.dump(cert_data, cert_file)
print(CERT+" configuration deleted")
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
   delcert )
      if [ -z "$2" ]
      then
        $0
        exit 1
      fi
      delcert $2
      ;;
   * )
      echo ""
      echo "usage:"
      echo "   -  $0 addcert"
      echo "   -  $0 delcert LABEL"
   esac