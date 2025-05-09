import json,sys,os,inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir) 

from modules.base import classes,configs

USR=sys.argv[1]
APPSRV=sys.argv[2]
APPSRVTYPE=sys.argv[3]

try:
   avl_data = configs.getAvlData()
except Exception as err:
   print("No such configuration file - config/confavl.json")
try:
   avl_data[APPSRVTYPE][APPSRV]["enabled"]="yes"
   with open(os.getcwd()+"/config/confavl.json", 'w+') as avl_file:
      json.dump(avl_data, avl_file)
   classes.WriteData("started,"+USR,"avl_"+APPSRVTYPE+"_"+APPSRV+".csv")
   print("Availability check for "+APPSRV+" have been started")
except Exception as err:
   print("No such availability for:"+APPSRV)
