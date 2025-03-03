import base64
import json,sys,os,inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir) 

from modules.base import configs

USR=sys.argv[1]
APPSRV=sys.argv[2]
APPSRVTYPE=sys.argv[3]
DOCKERCONT = sys.argv[4] if len(sys.argv) >= 5 else ''
USR = sys.argv[5] if len(sys.argv) >= 6 else ''
PWD = sys.argv[6] if len(sys.argv) >= 7 else ''
if PWD != '':
   PWD = base64.b64encode(PWD.encode()).decode('ascii')

def createAvlJson():
   try:
      avl_data = configs.getAvlData()
   except Exception as err:
      avl_data = {}

   try:
      avl_data[APPSRVTYPE][APPSRV] = {
       "enabled": "yes",
       "monid": "monapplavl",
       "dockercont": DOCKERCONT,
       "usr": USR,
       "pwd": PWD
      }
   except:
      avl_data[APPSRVTYPE] = {}
      avl_data[APPSRVTYPE][APPSRV] = {
       "enabled": "yes",
       "monid": "monapplavl",
       "dockercont": DOCKERCONT,
       "usr": USR,
       "pwd": PWD
      }

   with open(os.getcwd()+"/config/confavl.json", 'w+') as avl_file:
      json.dump(avl_data, avl_file)
   print("Availability check for "+APPSRV+" have been enabled")
    
if __name__ == "__main__":
   createAvlJson()
