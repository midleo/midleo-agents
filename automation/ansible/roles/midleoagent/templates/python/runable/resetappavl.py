import base64,platform,json,re,uuid,time,subprocess,socket,sys,os,inspect
from datetime import datetime

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir) 

from modules.base import makerequest,classes,configs,statarr,file_utils

if platform.system()=="Linux":
   from modules.base import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules.base import win_utils
else:
   exit()

YM=sys.argv[1]
WD=sys.argv[2]

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
