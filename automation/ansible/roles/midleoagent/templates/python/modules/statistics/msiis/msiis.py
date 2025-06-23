import base64
import csv
import hashlib
from Crypto.Hash import MD4

_original_hashlib_new = hashlib.new

def md4_patched(name, data=b''):
    if name == 'md4':
        h = MD4.new()
        h.update(data)
        return h
    return _original_hashlib_new(name, data)

hashlib.new = md4_patched

import json,glob,winrm
import os
import subprocess
from modules.base import makerequest,classes,configs,file_utils,statarr
from modules.statistics.msiis.modules import srvinfo

def getStat(thisqm,inpdata):
   try:
      inpdata=json.loads(inpdata)
      script_dir = os.path.dirname(os.path.abspath(__file__))
      jar_path = os.path.join(script_dir, "resources", "midleo_jboss.jar")
      usr_value = ""
      pwd_value = ""
      mngm_port = ""
      def_ssl = "https" if "ssl" in inpdata else "http"
      pwd_value = base64.b64decode(inpdata['pwd'] + "=" * (4 - len(inpdata['pwd']) % 4)).decode("utf-8") if 'pwd' in inpdata and inpdata['pwd'] else ""
      if "usr" in inpdata:
         usr_value = inpdata["usr"]
         del inpdata["usr"]
      if "pwd" in inpdata:
         del inpdata["pwd"]
      if "mngmport" in inpdata:
         mngm_port = inpdata["mngmport"]
         del inpdata["mngmport"]
      if "ssl" in inpdata:
         del inpdata["ssl"]
      session_url = f"{def_ssl}://{thisqm}:{mngm_port}/wsman"
      for key, val in inpdata.items():
         try:
            session = winrm.Session(
              session_url,
              auth=(usr_value, pwd_value),
              transport='ntlm',
              server_cert_validation='ignore',
              operation_timeout_sec=10,
            )
            ps_script = srvinfo.SRVFUNC()[key] if hasattr(srvinfo, 'SRVFUNC') and key in srvinfo.SRVFUNC() else None
            if ps_script:
              ps_script = ps_script.format(serverName=thisqm)
              result = session.run_ps(ps_script)
              output = result.std_out.decode('utf-8', errors='ignore')
#             error = result.std_err.decode('utf-8', errors='ignore')
              try:
                json_data = json.loads(output)
                if isinstance(json_data, list):
                   headers = json_data[0].keys() if json_data else []
                   filename = os.path.join(val, f"Statistics_{key}.csv")
                   file_exists = os.path.isfile(filename)
                   with open(filename, mode='a', newline='') as csvfile:
                      writer = csv.DictWriter(csvfile, fieldnames=headers)
                      if not file_exists:
                        writer.writeheader()
                      for row in json_data:
                         writer.writerow(row)
              except Exception as e:
                classes.Err(f"Error processing json_data: {e}")
                return

         except Exception as e:
            classes.Err(f"Error processing input data: {e}")
            return
      
   except json.JSONDecodeError as e:
      classes.Err("Error decoding JSON:"+e)
   except subprocess.SubprocessError as e:
      classes.Err("Error running Java command:"+e)

def resetStat(thisnode,website,webssl,inttoken,stat_data):
    try:
       if len(stat_data)>0:
          for k,item in stat_data.items():
             func = getattr(statarr, "msiis", None)
             files = glob.glob(item+"Statistics_"+k+".csv")
             for file in files:
                ret=file_utils.csv_json(file,func(),"",True)
                retarr=json.loads(ret)
                if len(retarr)>0:
                   ret={}
                   ret["type"]="msiis"
                   ret["inttoken"]=inttoken
                   ret["subtype"]=k
                   ret["data"]=retarr
                   makerequest.postStatData(webssl,website,json.dumps(ret))  

    except OSError as err:
       classes.Err("Error opening the file statlist:"+str(err))