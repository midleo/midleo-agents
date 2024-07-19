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

QMGR=sys.argv[1]

try:
   track_data = configs.gettrackData()
except Exception as err:
   print("No such configuration file - config/conftrack.json")
track_data.pop(QMGR, None)
with open(os.getcwd()+"/config/conftrack.json", 'w+') as track_file:
   json.dump(track_data, track_file)
print(QMGR+" configuration deleted")