import base64,platform,json,re,time,subprocess,socket,os,zlib, glob,inspect, sys
from datetime import datetime, timedelta

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir) 

from modules.base import makerequest,decrypt,classes,certcheck,configs,file_utils,statarr
from midleo_client import AGENT_VER

if platform.system()=="Linux":
   from modules.base import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules.base import win_utils
else:
   exit()


def create():
    try:
        config_data = configs.getcfgData()
        uid = config_data['uid']
        groupid = config_data['groupid']
        updint = config_data['updint']
        inttoken = config_data['inttoken']
        
        if platform.system()=="Windows":
            cpu = classes.CPU(win_utils.getCPUName(), win_utils.getCPUCoreCount())
            hw_config = classes.HWConfig(win_utils.getName(), win_utils.getOS(), win_utils.getArchitecture(), win_utils.getMachineType(), cpu.__dict__, win_utils.getMemory(), win_utils.getDiskPartitions(), win_utils.getLBTS())
            net_config = classes.NetConfig(win_utils.getIP())
            config = classes.Config(uid,inttoken,groupid,AGENT_VER,updint, hw_config.__dict__, net_config.__dict__, win_utils.getSoftware()) 
        elif platform.system()=="Linux":
            cpu = classes.CPU(lin_utils.getCPUName(), lin_utils.getCPUCoreCount())
            hw_config = classes.HWConfig(lin_utils.getName(), lin_utils.getOS(), lin_utils.getArchitecture(), lin_utils.getMachineType(), cpu.__dict__, lin_utils.getMemory(), lin_utils.getDiskPartitions(), lin_utils.getLBTS())
            net_config = classes.NetConfig(lin_utils.getIP())
            if os.path.isfile(os.getcwd()+"/config/certs.json"):
               cert_check = certcheck.Run(uid+uid+uid+uid)
            else:
               cert_check = []
            config = classes.Config(uid,inttoken,groupid,AGENT_VER,updint, hw_config.__dict__, net_config.__dict__, lin_packages.getSoftware(), cert_check) 
        else:
            exit()

        return config
    except OSError as err:
        classes.Err("Error in create:"+str(err))
    except Exception as ex:
        classes.Err("Exception in create:"+str(ex))

def main():
    config = create()
    config_data = configs.getcfgData()
    website = config_data['website']
    webssl = config_data['webssl']
    updint = int(config_data['updint'])

    if 'error' in config.__dict__.keys():
        return

    try:
        output = json.dumps(config.__dict__)
        output = re.sub(r"<([a-zA-Z-_]+)?.([a-zA-Z-_]+)(\d?):(\s?)", "", output)
        output = re.sub(r">", "", output)
        makerequest.postData(webssl,website,json.loads(output))
        timenow=datetime.now() + timedelta(minutes=updint)

        with open(os.getcwd()+"/config/nextrun.txt", 'w+') as log_file:
            log_file.write(str(timenow.strftime('%s')))

    except OSError as err:
        classes.Err("Error in main:"+str(err))
    except Exception as ex:
        classes.Err("Exception in main:"+str(ex))

if __name__ == '__main__':
   main()