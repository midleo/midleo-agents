import json,os,sys,inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir) 

from modules.base import classes,configs
from modules.statistics.ibmmq import ibmmq

if len(sys.argv) != 3:
   print("Usage: python ibmmqdocker.py <thisqm> <inpdata_json>")
   sys.exit(1)

thisqm = sys.argv[1]
inpdata_json = sys.argv[2]
inpdata_json = json.loads(inpdata_json)

try:
   mon_data = configs.getmonData()
   config_data = configs.getcfgData()
   website = config_data['MWADMIN']
   webssl = config_data['SSLENABLED']

   runstat=ibmmq.getStat(thisqm,json.dumps(inpdata_json))
          
except Exception as err:
   classes.Err("ibmmqdocker error:"+str(err))

