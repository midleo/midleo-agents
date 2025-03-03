import json,sys,os,inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir) 

from modules.base import configs

APPSRV=sys.argv[1]
APPSRVTYPE=sys.argv[2]

try:
   avl_data = configs.getAvlData()
except Exception as err:
   print("No such configuration file - config/confavl.json")
if APPSRVTYPE in avl_data:
   avl_data[APPSRVTYPE].pop(APPSRV, None)
with open(os.getcwd()+"/config/confavl.json", 'w+') as avl_file:
   json.dump(avl_data, avl_file)
print("Availability check for "+APPSRV+" have been disabled")
   