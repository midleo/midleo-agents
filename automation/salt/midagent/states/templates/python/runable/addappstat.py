import base64,platform,json,re,uuid,time,sys,os,inspect
from datetime import datetime

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir) 

from modules.base import classes,configs

if platform.system()=="Linux":
   from modules.base import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules.base import win_utils
else:
   exit()

SRVTYPE=sys.argv[1]
APPSRV=sys.argv[2]
STDATA=sys.argv[3]

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
