import json,glob
import os
import subprocess
from modules.base import makerequest,classes,configs,file_utils,statarr

def getStat(thisqm,inpdata):
   try:
      inpdata=json.loads(inpdata)
      script_dir = os.path.dirname(os.path.abspath(__file__))
      jar_path = os.path.join(script_dir, "resources", "midleo_jboss.jar")
      usr_value = ""
      pwd_value = ""
      if "usr" in inpdata:
         usr_value = inpdata["usr"]
         del inpdata["usr"]
      if "pwd" in inpdata:
         pwd_value = inpdata["pwd"]
         del inpdata["pwd"]
      for kin,vin in inpdata.items():
         java_arg = json.dumps({"logdir": vin, "mbean": kin, "function": "getstat", "usr": usr_value, "pwd": pwd_value})
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
   return