import base64,platform,json,re,uuid,time,subprocess,socket,sys,os,inspect
from datetime import datetime

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir) 

from modules.base import makerequest,classes,configs

if platform.system()=="Linux":
   from modules.base import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules.base import win_utils
else:
   exit()

AMQSEVT=sys.argv[1]

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
