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

export DSPMQ
export DSPMQVER
export AMQSEVT
export RUNMQSC
export ACEUSR
export MQSIPROFILE

YM=$(date '+%Y-%m')
WD=$(date '+%d')
HOUR=$(date '+%H%M')

if [[ ! -e $HOMEDIR ]]; then
    mkdir $HOMEDIR
fi

load_config ()
{
   if [ -e "$HOMEDIR/midleoclient.conf" ]; then
      . $HOMEDIR/midleoclient.conf
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
   classes.Err("No such configuration file - config/conftrack.json."+err) 

EOF
fi
}

resetappavl (){
if [ -e "$HOMEDIR/confavl.json" ]; then
  /usr/bin/python3 << EOF
import base64,platform,json,re,uuid,time,subprocess,socket,sys,os
from datetime import datetime
from modules import makerequest,classes,configs,statarr,file_utils

if platform.system()=="Linux":
   from modules import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules import win_utils
else:
   exit()

YM="$YM"
WD="$WD"

try:
   avl_data = configs.getAvlData()
   config_data = configs.getcfgData()
   website = config_data['website']
   webssl = config_data['webssl']
   uid = config_data['uid']
   if len(avl_data)>0:
      for k,item in avl_data.items():
         ret=file_utils.ReadAvl("avl_"+k+".csv")
         if 'navl' in ret:
            ret["appsrv"]=k
            ret["srvid"]=uid
            ret["srvtype"]=item["type"]
            ret["thismonth"]=YM
            ret["thisdate"]=WD
            makerequest.postAvlData(webssl,website,json.dumps(ret))

except Exception as err:
   classes.Err("No such configuration file - config/conftrack.json."+err)

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
   classes.Err("No such configuration file - config/conftrack.json."+err) 

EOF
fi
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
      for qm in mon_data:
         value = mon_data[qm]
         for q,val in value.items():
            qinfo=makerequest.getJQstat(JAVA_OPTS,qm,q,val["thres"])
            if(qinfo!="{}" and qinfo is not None):
              makerequest.postQData(webssl,website,qm,q,qinfo)
   except Exception as err:
      classes.Err("MQMON not configured err:"+err)

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

      for qm in mon_data:
        value = mon_data[qm]
        for q,val in value.items():
          qinfo=makerequest.getQStat(SSL,HOST,PORT,qm,q,USR,PASS)
          if(qinfo!="{}" and qinfo is not None):
            makerequest.postQData(webssl,website,qm,q,qinfo)
   except Exception as err:
      classes.Err("MQWEB not configured err:"+err)
   
EOF
}

case "$1" in
    help )
      echo "Cronjobs for MWAdmin"
      echo "Used for background processes"
      ;;
    * )
      load_config
      if [ -n "$mainver" ]; then
         runmqjob
         runmqtracker
      fi
      if [ $HOUR == "2359" ]; then
        resetappavl
      else
        runappavl
      fi
      ;;
   esac