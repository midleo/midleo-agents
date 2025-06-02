import json,glob
import os
import subprocess
from modules.base import makerequest,classes,configs,file_utils,statarr

def getStat(thisqm,inpdata):
   try:
      inpdata=json.loads(inpdata)
      script_dir = os.path.dirname(os.path.abspath(__file__))
      jar_path = os.path.join(script_dir, "resources", "midleo_weblogic.jar")
      usr_value = ""
      pwd_value = ""
      mngm_port = ""
      ssl = "no"
      if "usr" in inpdata:
         usr_value = inpdata["usr"]
         del inpdata["usr"]
      if "pwd" in inpdata:
         pwd_value = inpdata["pwd"]
         del inpdata["pwd"]
      if "mngmport" in inpdata:
         mngm_port = inpdata["mngmport"]
         del inpdata["mngmport"]
      if "ssl" in inpdata:
         ssl = inpdata["ssl"]
         del inpdata["ssl"]
      mbean_list = [kin for kin in inpdata.keys()]
      mbeans_combined = ",".join(mbean_list)
      logdir = next(iter(inpdata.values()))

      java_arg = json.dumps({
        "logdir": logdir,
        "server": thisqm,
        "mbean": mbeans_combined,
        "function": "getstat",
        "usr": usr_value,
        "pwd": pwd_value,
        "mngmport": mngm_port,
        "ssl": ssl
      })

      command = [
         "java",
         "--add-opens", "java.base/java.io=ALL-UNNAMED",
         "-cp", "/midleolibs/libs/*:/midleolibs/vendor/*:" + jar_path,
         "midleo_weblogic.weblogic_main",
         java_arg
      ]
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
             func = getattr(statarr, "weblogic", None)
             files = glob.glob(item+"Statistics_"+k+".csv")
             for file in files:
                ret=file_utils.csv_json(file,func(),"",True)
                retarr=json.loads(ret)
                if len(retarr)>0:
                   ret={}
                   ret["type"]="weblogic"
                   ret["inttoken"]=inttoken
                   ret["subtype"]=k
                   ret["data"]=retarr
                   makerequest.postStatData(webssl,website,json.dumps(ret))  

    except OSError as err:
       classes.Err("Error opening the file statlist:"+str(err))