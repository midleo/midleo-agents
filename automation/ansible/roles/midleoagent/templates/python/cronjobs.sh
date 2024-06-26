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

if [[ ! -z "${PYTHON_PATH}" ]]; then
  PYTHON=${PYTHON_PATH}
else
  PYTHON="{{python_install_dir}}"
fi


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

LRFILE=$HOMEDIR"/nextrun.txt"
if [ -e "$LRFILE" ]; then
  TST=$(head -n 1 $LRFILE)
  if [ -z "$TST" ]; then
     TST=$(date '+%Y-%m-%dT%H:%M')
  fi
else
  TST=$(date '+%Y-%m-%dT%H:%M')
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
   inttoken = config_data['inttoken']
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
                  req["inttoken"]=inttoken
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
   inttoken = config_data['inttoken']
   uid = config_data['uid']
   if len(avl_data)>0:
      for k,item in avl_data.items():
         ret=file_utils.ReadAvl("avl_"+k+".csv")
         if 'navl' in ret:
            ret["appsrv"]=k
            ret["srvid"]=uid
            ret["inttoken"]=inttoken
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
   inttoken = config_data['inttoken']
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
                            ret["inttoken"]=inttoken
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
   inttoken = config_data['inttoken']
   for k,item in mon_data.items():
       for q,val in item.items():
          resstat=eval(k+'.resetStat(q,website,webssl,inttoken,val)')
       
except Exception as err:
   classes.Err("MQSTAT not configured err:"+err)

EOF
}

getsrvdata(){
$PYTHON << EOF
import base64,platform,json,re,time,subprocess,socket,os,zlib, glob
from datetime import datetime, timedelta, timezone
from modules.base import makerequest,decrypt,classes,certcheck,configs,file_utils,statarr
from midleo_client import AGENT_VER

if platform.system()=="Linux":
   from modules.base import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules.base import win_utils
else:
   exit()


def create():
    try:
        config_data = configs.getcfgData()
        uid = config_data['uid']
        groupid = config_data['groupid']
        updint = config_data['updint']
        inttoken = config_data['inttoken']
        
        if platform.system()=="Windows":
            cpu = classes.CPU(win_utils.getCPUName(), win_utils.getCPUCoreCount())
            hw_config = classes.HWConfig(win_utils.getName(), win_utils.getOS(), win_utils.getArchitecture(), win_utils.getMachineType(), cpu.__dict__, win_utils.getMemory(), win_utils.getDiskPartitions(), win_utils.getLBTS())
            net_config = classes.NetConfig(win_utils.getIP())
            config = classes.Config(uid,inttoken,groupid,AGENT_VER,updint, hw_config.__dict__, net_config.__dict__, win_utils.getSoftware()) 
        elif platform.system()=="Linux":
            cpu = classes.CPU(lin_utils.getCPUName(), lin_utils.getCPUCoreCount())
            hw_config = classes.HWConfig(lin_utils.getName(), lin_utils.getOS(), lin_utils.getArchitecture(), lin_utils.getMachineType(), cpu.__dict__, lin_utils.getMemory(), lin_utils.getDiskPartitions(), lin_utils.getLBTS())
            net_config = classes.NetConfig(lin_utils.getIP())
            if os.path.isfile(os.getcwd()+"/config/certs.json"):
               cert_check = certcheck.Run(uid+uid+uid+uid)
            else:
               cert_check = []
            config = classes.Config(uid,inttoken,groupid,AGENT_VER,updint, hw_config.__dict__, net_config.__dict__, lin_packages.getSoftware(), cert_check) 
        else:
            exit()

        return config
    except OSError as err:
        classes.Err("Error in create:"+str(err))
    except Exception as ex:
        classes.Err("Exception in create:"+str(ex))

def main():
    config = create()
    config_data = configs.getcfgData()
    website = config_data['website']
    webssl = config_data['webssl']
    updint = int(config_data['updint'])

    if 'error' in config.__dict__.keys():
        return

    try:
        output = json.dumps(config.__dict__)
        output = re.sub(r"<([a-zA-Z-_]+)?.([a-zA-Z-_]+)(\d?):(\s?)", "", output)
        output = re.sub(r">", "", output)
        makerequest.postData(webssl,website,json.loads(output))
        timenow=datetime.now() + timedelta(minutes=updint)

        with open(os.getcwd()+"/config/nextrun.txt", 'w+') as log_file:
            log_file.write(str(timenow.strftime('%Y-%m-%dT%H:%M')))

    except OSError as err:
        classes.Err("Error in main:"+str(err))
    except Exception as ex:
        classes.Err("Exception in main:"+str(ex))

if __name__ == '__main__':
   main()

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
      if [ $TST == $(date '+%Y-%m-%dT%H:%M') ]; then
         getsrvdata
      fi
      ;;
   esac