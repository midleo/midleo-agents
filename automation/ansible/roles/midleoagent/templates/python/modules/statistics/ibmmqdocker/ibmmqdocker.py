import json,glob
import os
import subprocess
from modules.base import makerequest,classes,configs,file_utils,statarr


def getStat(thisqm,inpdata):
    try:
        inpdata=json.loads(inpdata)
        container = ""
        if "container" in inpdata:
          container = inpdata["container"]
          del inpdata["container"]
        thisscript=os.environ['MWAGTDIR']+"/magent_docker.sh getibmmqdockerstat "+thisqm+" '"+json.dumps(inpdata)+"'"
        command = ["docker", "exec", container, "bash", "-c", thisscript]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.stdout:
            classes.Err("Output:"+result.stdout)
        if result.stderr:
            classes.Err("Error:"+result.stderr)
        if result.returncode != 0:
            classes.Err("Command failed with exit code "+result.returncode)


    except OSError as err:
       classes.Err("Error opening the file ibmmqdocker:"+str(err))