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

try:
   mon_data = configs.getmonData()
except Exception as err:
   print("No such configuration file - config/confapplstat.json")
mon_data[SRVTYPE].pop(APPSRV, None)
with open(os.getcwd()+"/config/confapplstat.json", 'w+') as mon_file:
   json.dump(mon_data, mon_file)
print(APPSRV+" configuration deleted")