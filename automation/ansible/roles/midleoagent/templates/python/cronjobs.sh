#!/bin/bash

#script for midleo.CORE agent
#created by V.Vasilev
#https://vasilev.link

HOMEDIR=$(pwd)"/config"
DSPMQVER=/opt/mqm/bin/dspmqver
DSPMQ=/opt/mqm/bin/dspmq
RUNMQSC=/opt/mqm/bin/runmqsc
AMQSEVT=/opt/mqm/bin/amqsevt
ACEUSR=mqbrk
MQSIPROFILE=/opt/ibm/ace/server/bin/mqsiprofile

export DSPMQ
export DSPMQVER
export AMQSEVT
export RUNMQSC
export ACEUSR
export MQSIPROFILE

cd $(dirname $0)

if [[ ! -e $HOMEDIR ]]; then
    mkdir $HOMEDIR
fi

load_config ()
{
   if [ -e "$HOMEDIR/midleoclient.conf" ]; then
      . $HOMEDIR/midleoclient.conf
   else
      create_config
   fi
}
create_config (){
    echo "Midleo DNS server name:"
    read midleodns
    if [ -z "${midleodns}" ]; then
       rm $HOMEDIR/"midleoclient.conf"
    else
       echo "midleodns=$midleodns" > $HOMEDIR/"midleoclient.conf"
    fi
    echo "IBM MQ library path(example - /opt/mqm/java/lib64):"
    read ibmmqlibpath
    if [ -z "${ibmmqlibpath}" ]; then
       rm $HOMEDIR/"midleoclient.conf"
    else
       echo ibmmqlibpath=$ibmmqlibpath >> $HOMEDIR/"midleoclient.conf"
    fi
    if test -f "$DSPMQVER"; then
      mainver=`$DSPMQVER | grep Version | awk '{print $2}' | cut -d '.' -f 1`
      echo mainver=$mainver >> $HOMEDIR/"midleoclient.conf"
    fi
    if [ -n "$mainver" ] && [ $mainver -gt 8 ]; then
      echo mqwebhost=`hostname -f` >> $HOMEDIR/"midleoclient.conf"
      echo "IBM MQWeb user:"
      read ibmmqwebusr
      echo ibmmqwebusr=$ibmmqwebusr >> $HOMEDIR/"midleoclient.conf"
      echo "IBM MQWeb password:"
      read -s ibmmqwebusrpwd
      echo ibmmqwebusrpwd=`echo $ibmmqwebusrpwd | base64`  >> $HOMEDIR/"midleoclient.conf"
      echo "IBM MQWeb SSL enabled(y/n):"
      read ibmmqwebssl
      echo ibmmqwebssl=$ibmmqwebssl >> $HOMEDIR/"midleoclient.conf"
      echo "IBM MQWeb port:"
      read mqwebport
      echo mqwebport=$mqwebport >> $HOMEDIR/"midleoclient.conf"
    fi
}

runmqjob (){
JAVA_OPTS="-Djava.library.path=$ibmmqlibpath"
if [ -n "$mainver" ] && [ $mainver -gt 8 ]; then
  runmqweb $ibmmqwebssl $mqwebhost $mqwebport $ibmmqwebusr $ibmmqwebusrpwd
else
  runmqmon $JAVA_OPTS
fi
}

runappavl(){
if [ -e "$HOMEDIR/confavl.json" ]; then
  /usr/bin/python3 << EOF
import base64,platform,json,re,uuid,time,subprocess,socket,sys,os
from datetime import datetime
from modules import makerequest,classes,configs,statarr

if platform.system()=="Linux":
   from modules import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules import win_utils
else:
   exit()

try:
   avl_data = configs.getAvlData()
   config_data = configs.getcfgData()
   website = config_data['website']
   webssl = config_data['webssl']
   if len(avl_data)>0:
      for k,item in avl_data.items():
         ret=statarr.avlCheck(k)
         if(item["enabled"]=='yes'):
           ret=ret[item["type"]]
           try:
             output = subprocess.run(ret,shell=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
             output = output.stdout.decode()
             if(int(output)==1):
               classes.WriteData("online","avl_"+k+".csv")
             else:
               classes.WriteData("offline","avl_"+k+".csv")
           except subprocess.CalledProcessError as e:
             classes.Err("avlCheck err:"+e.output)
except Exception as err:
   print("No such configuration file - config/conftrack.json") 

EOF

fi
}

runmqtracker (){
if [ -f $HOMEDIR"/conftrack.json" ]; then
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

AMQSEVT="$AMQSEVT"

try:
   track_data = configs.gettrackData()
   config_data = configs.getcfgData()
   website = config_data['website']
   webssl = config_data['webssl']
   if len(track_data)>0:
      for k,item in track_data.items():
         try:
            output = subprocess.run("sudo su - mqm -c '"+AMQSEVT+" -m "+k+" -q SYSTEM.ADMIN.TRACE.ACTIVITY.QUEUE -w 1 -o json | jq . -c --slurp'",shell=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            output = output.stdout.decode()
            try:
               out = json.loads(output)
               if len(out)>0:
                  for event in out:
                     eventData = event["eventData"]
                     if "channelName" in eventData: 
                         channelName = eventData["channelName"]
                         connectionName = eventData["connectionName"]
                     else:     
                          channelName = "Local"
                          connectionName = "Local     "
                     app = eventData["applName"]
                     actTr = eventData["activityTrace"]
                     for act in actTr:
                         if act["operationId"] in ["Put1","Put","Get","Cb","Callback"] and act["objectName"]!="SYSTEM.ADMIN.TRACE.ACTIVITY.QUEUE":
                            ret={}
                            ret["qmgr"]=k
                            ret["objectName"]=act["objectName"]
                            ret["applName"] = app
                            ret["channelName"]= channelName
                            ret["connectionName"] = connectionName
                            ret["trackdata"]=act
                            makerequest.postTrackData(webssl,website,json.dumps(ret))
            except:
               classes.Err("Return error:"+output)
         except subprocess.CalledProcessError as e:
            classes.Err("amqsevt err:"+e.output)
   
except Exception as err:
   print("No such configuration file - config/conftrack.json") 

EOF
fi
}

enabletrackqm (){
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

runmqmon(){
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

JAVA_OPTS="$1"

if __name__ == "__main__":
   try:
      mon_data = configs.getmonData()
   except Exception as err:
      mon_data = {}
   for qm in mon_data:
      value = mon_data[qm]
      for q,val in value.items():
        qinfo=makerequest.getJQstat(JAVA_OPTS,qm,q,val["thres"])
        if(qinfo!="{}" and qinfo is not None):
          makerequest.postQData(webssl,website,qm,q,qinfo)   

EOF
}

runmqweb(){
/usr/bin/python3 << EOF
import base64,platform,json,re,uuid,time,subprocess,socket,sys,os,requests
from datetime import datetime
from modules import makerequest,classes,configs
if platform.system()=="Linux":
   from modules import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules import win_utils
else:
   exit()

SSL="$1"
HOST="$2"
PORT="$3"
USR="$4"
PASS="$5"

if __name__ == "__main__":
   try:
      mon_data = configs.getmonData()
      config_data = configs.getcfgData()
      website = config_data['website']
      webssl = config_data['webssl']
   except Exception as err:
      mon_data = {}
   for qm in mon_data:
      value = mon_data[qm]
      for q,val in value.items():
        qinfo=makerequest.getQStat(SSL,HOST,PORT,qm,q,USR,PASS)
        if(qinfo!="{}" and qinfo is not None):
          makerequest.postQData(webssl,website,qm,q,qinfo)

EOF
}

addmon(){
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

QMGR="$1"
QUEUE="$2"
TMON="$3"
THRES="$4"

def createMonJson():
   try:
      mon_data = configs.getmonData()
   except Exception as err:
      mon_data = {}
   try:
     mon_data[QMGR][QUEUE] = {
      "type": TMON,
      "thres": THRES
     }
   except Exception as err: 
     mon_data[QMGR] = {}
     mon_data[QMGR][QUEUE] = {
      "type": TMON,
      "thres": THRES
     }

   with open(os.getcwd()+"/config/confmon.json", 'w+') as mon_file:
      json.dump(mon_data, mon_file)
   print(QUEUE+" on "+QMGR+" have been added")
    
if __name__ == "__main__":
   createMonJson()

EOF
}

delmon(){
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

QMGR="$1"
QUEUE="$2"

try:
   mon_data = configs.getmonData()
except Exception as err:
   print("No such configuration file - config/confmon.json")
mon_data[QMGR].pop(QUEUE, None)
with open(os.getcwd()+"/config/confmon.json", 'w+') as mon_file:
   json.dump(mon_data, mon_file)
print(QUEUE+" configuration deleted")
EOF
}

case "$1" in
	 addmonq )
      addmon $2 $3 $4 $5
      ;;
    addmonchl )
      addmon $2 $3 "CHANNELS"
      ;;
    delmonq )
      if [ -z "$2" ]
      then
        $0
        exit 1
      fi
      delmon $2 $3
      ;;
    delmonchl )
      if [ -z "$2" ]
      then
        $0
        exit 1
      fi
      delmon $2 $3
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
    help )
      echo ""
      echo "Usage:"
      echo " - $0 addconf QMGR WebUser(Optional) WebPassword(Optional)"
      echo " - $0 addmonq QMGR QUEUE TYPE_OF_MON THRESHOLD"
      echo " - $0 delmonq QMGR QUEUE"
      echo " - $0 enabletrackqm QMGR # Transfer the mqat.ini file to /var/mqm/qmgr/QMGR/ folder"
      echo " - $0 disabletrackqm QMGR"
      echo " - $0 addmonchl QMGR CHANNEL"
      echo " - $0 delmonchl QMGR CHANNEL"
      echo ""
      echo "Parameters:"
      echo " - TYPE_OF_MON: QAGE - monitor queue age, QFULL - monitor percentage of maxdepth/curdepth"
      echo " -   THRESHOLD: threshold in percent for QFULL/seconds for QAGE (more than this value will be taken in the report)"
      ;;
    * )
      load_config
#      runmqjob
      runappavl
      runmqtracker
      ;;
   esac