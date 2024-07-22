import json,os,sys,inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir) 

from modules.base import classes,configs
for entry in os.scandir('modules/statistics'):
    if entry.is_dir() and entry.name!='__pycache__':
       string = f'from modules.statistics.{entry.name} import {entry.name}'
       exec (string)

try:
   mon_data = configs.getmonData()
   config_data = configs.getcfgData()
   website = config_data['website']
   webssl = config_data['webssl']
   for k,item in mon_data.items():
       for q,val in item.items():
          runstat=eval(k+'.getStat(q,json.dumps(val))')
       
except Exception as err:
   classes.Err("getapplstat error:"+str(err))
