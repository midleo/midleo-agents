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
CM=$(date +%M)

if [[ ! -e $HOMEDIR ]]; then
    mkdir $HOMEDIR
fi

runappavl(){
if [ -e "$HOMEDIR/confavl.json" ]; then
  $PYTHON << EOF
import base64,platform,json,re,uuid,time,subprocess,socket,sys,os
from datetime import datetime
from modules.base import makerequest,classes,configs,statarr

if platform.system()=="Linux":
   from modules.base import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules.base import win_utils
else:
   exit()

now = datetime.now()
current_time = now.strftime("%Y-%m-%d %H:%M:%S")

try:
   avl_data = configs.getAvlData()
   config_data = configs.getcfgData()
   website = config_data['website']
   webssl = config_data['webssl']
   uid = config_data['uid']
   if len(avl_data)>0:
      for k,item in avl_data.items():
         if("dockercont" in item):
            ret=statarr.avlCheck(k,item["dockercont"])
         else:
            ret=statarr.avlCheck(k)
         if(item["enabled"]=='yes'):
           ret=ret[item["type"]]
           try:
             output = subprocess.run(ret,shell=True,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
             output = output.stdout.decode()
             if(int(output)==1):
               classes.WriteData("online","avl_"+k+".csv")
             else:
               classes.WriteData("offline","avl_"+k+".csv")
               if("monid" in item):
                  req={}
                  req["appsrv"]=k
                  req["monid"]=item["monid"]
                  req["srvid"]=uid
                  req["srvtype"]=item["type"]
                  req["message"]="Server not available"
                  req["alerttime"]=current_time
                  makerequest.postMonAl(webssl,website,json.dumps(req))
           except subprocess.CalledProcessError as e:
             classes.Err("avlCheck err:"+str(e.output))
except Exception as err:
   classes.Err("No such configuration file - config/conftrack.json."+err) 

EOF
fi
}

resetappavl (){
if [ -e "$HOMEDIR/confavl.json" ]; then
  $PYTHON << EOF
import base64,platform,json,re,uuid,time,subprocess,socket,sys,os
from datetime import datetime
from modules.base import makerequest,classes,configs,statarr,file_utils

if platform.system()=="Linux":
   from modules.base import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules.base import win_utils
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
}

getapplstat(){
$PYTHON << EOF
import json,os
from modules.base import classes,configs
for entry in os.scandir('modules/statistics'):
    if entry.is_dir() and entry.name!='__pycache__':
       string = f'from modules.statistics.{entry.name} import {entry.name}'
       exec (string)

try:
   mon_data = configs.getmonData()
   config_data = configs.getcfgData()
   website = config_data['website']
   webssl = config_data['webssl']
   for k,item in mon_data.items():
       for q,val in item.items():
          runstat=eval(k+'.getStat(q,json.dumps(val))')
       
except Exception as err:
   classes.Err("MQSTAT not configured err:"+err)

EOF
}


resetapplstat(){
$PYTHON << EOF
import os
from modules.base import classes,configs
for entry in os.scandir('modules/statistics'):
    if entry.is_dir() and entry.name!='__pycache__':
       string = f'from modules.statistics.{entry.name} import {entry.name}'
       exec (string)


try:
   mon_data = configs.getmonData()
   config_data = configs.getcfgData()
   website = config_data['website']
   webssl = config_data['webssl']
   for k,item in mon_data.items():
       for q,val in item.items():
          resstat=eval(k+'.resetStat(q,website,webssl)')
       exit()
       
except Exception as err:
   classes.Err("MQSTAT not configured err:"+err)

EOF
}


case "$1" in
    help )
      echo "Cronjobs for MWAdmin"
      echo "Used for background processes"
      ;;
    * )
      if [ -f $HOMEDIR"/confapplstat.json" ]; then
         if [[ $CM == "30" || $CM == "00" ]]; then
            resetapplstat
         else
            getapplstat
         fi
      fi
      if [ -f $HOMEDIR"/conftrack.json" ]; then
         runmqtracker
      fi
      if [ $HOUR == "2359" ]; then
        resetappavl
      else
        runappavl
      fi
      ;;
   esac