import json,sys,os,inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir) 

from modules.base import configs

USR=sys.argv[1]
APPSRV=sys.argv[2]
APPSRVTYPE=sys.argv[3]
DOCKERCONT = sys.argv[4] if len(sys.argv) >= 5 else ''

def createAvlJson():
   try:
      avl_data = configs.getAvlData()
   except Exception as err:
      avl_data = {}
   
   avl_data[APPSRV] = {
     "type": APPSRVTYPE,
     "enabled": "yes",
     "monid": "monapplavl",
     "dockercont": DOCKERCONT
   }

   with open(os.getcwd()+"/config/confavl.json", 'w+') as avl_file:
      json.dump(avl_data, avl_file)
   print("Availability check for "+APPSRV+" have been enabled")
    
if __name__ == "__main__":
   createAvlJson()
