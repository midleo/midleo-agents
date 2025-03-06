import json,os,sys,inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir) 

from modules.base import classes,configs
for entry in os.scandir('modules/statistics'):
    if entry.is_dir() and entry.name!='__pycache__':
       string = f'from modules.statistics.{entry.name} import {entry.name}'
       exec (string)

if len(sys.argv) != 3:
   print("input: <type> <thisqm> <inpdata_json>")
   sys.exit(1)

thistype = sys.argv[1]
thisqm = sys.argv[2]
inpdata_json = sys.argv[3]
inpdata_json = json.loads(inpdata_json)

try:
   mon_data = configs.getmonData()
   config_data = configs.getcfgData()
   website = config_data['MWADMIN']
   webssl = config_data['SSLENABLED']

   runstat=eval(thistype+'.getStat(thisqm,json.dumps(inpdata_json))')
          
except Exception as err:
   classes.Err("ibmmqdocker error:"+str(err))

