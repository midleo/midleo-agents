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
