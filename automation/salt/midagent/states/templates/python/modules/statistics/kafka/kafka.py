import json,glob
import os
import subprocess
from modules.base import makerequest,classes,configs,file_utils,statarr

def getStat(thisqm,inpdata):
   try:
      inpdata=json.loads(inpdata)
      script_dir = os.path.dirname(os.path.abspath(__file__))
      jar_path = os.path.join(script_dir, "resources", "midleo_kafka.jar")
      for kin,vin in inpdata.items():
         java_arg = json.dumps({"logdir": vin, "mbean": kin, "function": "localstat", "localbrk":thisqm})
         command = ["java", "-jar", jar_path, java_arg]
         result = subprocess.run(command, capture_output=True, text=True)
         if result.stdout:
            classes.Err("Output:"+result.stdout)
         if result.stderr:
            classes.Err("Error:"+result.stderr)
         if result.returncode != 0:
            classes.Err("Command failed with exit code "+result.returncode)

   
   except json.JSONDecodeError as e:
      classes.Err("Error decoding JSON:"+e)
   except subprocess.SubprocessError as e:
      classes.Err("Error running Java command:"+e)

def resetStat(thisnode,website,webssl,inttoken,stat_data):
    try:
       if len(stat_data)>0:
          for k,item in stat_data.items():
             func = getattr(statarr, "kafka"+k, None)
             files = glob.glob(item+"Statistics_"+k+".csv")
             for file in files:
                ret=file_utils.csv_json(file,func(),"",True)
                retarr=json.loads(ret)
                if len(retarr)>0:
                   ret={}
                   ret["type"]="kafka"
                   ret["inttoken"]=inttoken
                   ret["subtype"]=k
                   ret["data"]=retarr
                   makerequest.postStatData(webssl,website,json.dumps(ret))  

    except OSError as err:
       classes.Err("Error opening the file statlist:"+str(err))