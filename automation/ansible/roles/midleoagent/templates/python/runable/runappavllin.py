import base64,platform,json,re,uuid,time,subprocess,socket,sys,os,inspect
from datetime import datetime

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir) 

from modules.base import makerequest,classes,configs,statarr

if platform.system()=="Linux":
   from modules.base import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules.base import win_utils
else:
   exit()

now = datetime.now()
current_time = now.strftime("%Y-%m-%d %H:%M:%S")

try:
   avl_data = configs.getAvlData()
   config_data = configs.getcfgData()
   website = config_data['website']
   webssl = config_data['webssl']
   inttoken = config_data['inttoken']
   uid = config_data['uid']
   if len(avl_data)>0:
      for k,item in avl_data.items():
         if("dockercont" in item):
            ret=statarr.avlCheck(k,item["dockercont"])
         else:
            ret=statarr.avlCheck(k)
         if(item["enabled"]=='yes'):
           ret=ret[item["type"]]
           try:
             output = subprocess.run(ret,shell=True,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
             output = output.stdout.decode()
             if(int(output)>=1):
               classes.WriteData("online","avl_"+k+".csv")
             else:
               classes.WriteData("offline","avl_"+k+".csv")
               if("monid" in item):
                  req={}
                  req["appsrv"]=k
                  req["monid"]=item["monid"]
                  req["srvid"]=uid
                  req["srvtype"]=item["type"]
                  req["message"]="Server not available"
                  req["alerttime"]=current_time
                  req["inttoken"]=inttoken
                  makerequest.postMonAl(webssl,website,json.dumps(req))
           except subprocess.CalledProcessError as e:
             classes.Err("avlCheck err:"+str(e.output))
except Exception as err:
   classes.Err("error in runappavl:"+str(err)) 
