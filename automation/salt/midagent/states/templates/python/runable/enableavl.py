import json,sys,os,inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir) 

from modules.base import decrypt,configs

APPSRV=sys.argv[1]
APPSRVTYPE=sys.argv[2]
MONDATA=sys.argv[3] if len(sys.argv) >= 4 else '{}'

def createAvlJson():
   config_data = configs.getcfgData()
   uid = config_data['SRVUID']

   if not uid:
      pass
   
   try:
      avl_data = configs.getAvlData()
   except Exception as err:
      avl_data = {}
   
   try:
      MONJSDATA=json.loads(MONDATA)
   except Exception as err:
      MONJSDATA={}

   try:
      avl_data[APPSRVTYPE][APPSRV] = {
       "enabled": "yes",
       "monid": "monapplavl",
       "dockercont": MONJSDATA['docker'] if 'docker' in MONJSDATA else '',
       "usr": MONJSDATA['user'] if 'user' in MONJSDATA else '',
       "ssl": MONJSDATA['ssl'] if 'ssl' in MONJSDATA else 'no',
       "appsrvid": MONJSDATA['appsrvid'] if 'appsrvid' in MONJSDATA else 'none',
       "mngmport": MONJSDATA['mngmport'] if 'mngmport' in MONJSDATA else '',
       "pwd": decrypt.encryptPWD(MONJSDATA["pass"]) if "pass" in MONJSDATA else ""
      }
   except:
      avl_data[APPSRVTYPE] = {}
      avl_data[APPSRVTYPE][APPSRV] = {
       "enabled": "yes",
       "monid": "monapplavl",
       "dockercont": MONJSDATA['docker'] if 'docker' in MONJSDATA else '',
       "usr": MONJSDATA['user'] if 'user' in MONJSDATA else '',
       "appsrvid": MONJSDATA['appsrvid'] if 'appsrvid' in MONJSDATA else 'none',
       "ssl": MONJSDATA['ssl'] if 'ssl' in MONJSDATA else 'no',
       "mngmport": MONJSDATA['mngmport'] if 'mngmport' in MONJSDATA else '',
       "pwd": decrypt.encryptPWD(MONJSDATA["pass"]) if "pass" in MONJSDATA else ""
      }

   with open(os.getcwd()+"/config/confavl.json", 'w+') as avl_file:
      json.dump(avl_data, avl_file)
   print("Availability check for "+APPSRV+" have been enabled")
    
if __name__ == "__main__":
   createAvlJson()
