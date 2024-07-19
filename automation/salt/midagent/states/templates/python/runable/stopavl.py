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

USR=sys.argv[1]
APPSRV=sys.argv[2]
COMMENT=sys.argv[3]

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
