import makerequest
import classes
import platform
import json
import re
import uuid
import time
import requests
import json

if platform.system()=="Linux":
    import lin_utils
    import lin_packages
elif platform.system()=="Windows":
    import win_utils
else:
    print('Not supported OS')

def getcfgData():
    with open('./agentConfig.json', 'r') as config_file:
        data=json.load(config_file)
        config_data = {}
        config_data['uid']=data['uid']
        config_data['website']=data['website']
        config_data['webssl']=data['webssl']
        config_data['groupid']=data['groupid']
        config_data['updint']=data['updint']
        return config_data

def createConfigJson():
    try:
        config_data = getcfgData()
    except Exception as err:

        config_data = {
            "uid": str(uuid.uuid4().hex[:16]),
            "website": input("Please provide midleo DNS:"),
            "webssl": input("SSL enabled ? (y/n):"),
            "groupid": input("Please provide responsible GroupID:"),
            "updint": input("Update interval (in minutes):")
        }

        with open('./agentConfig.json', 'w+') as config_file:
            json.dump(config_data, config_file)

def create():
    try:
        config_data = getcfgData()
        uid = config_data['uid']
        groupid = config_data['groupid']
        updint = config_data['updint']

        if platform.system()=="Windows":
            cpu = classes.CPU(win_utils.getCPUName(), win_utils.getCPUCoreCount())
            hw_config = classes.HWConfig(win_utils.getName(), win_utils.getOS(), win_utils.getArchitecture(), win_utils.getMachineType(), cpu.__dict__, win_utils.getMemory(), win_utils.getDiskPartitions(), win_utils.getLBTS())
            net_config = classes.NetConfig(win_utils.getDNS(), win_utils.getIFAddresses())
            config = classes.Config(uid,groupid,updint, hw_config.__dict__, net_config.__dict__, win_utils.getSoftware()) 
        elif platform.system()=="Linux":
            cpu = classes.CPU(lin_utils.getCPUName(), lin_utils.getCPUCoreCount())
            hw_config = classes.HWConfig(lin_utils.getName(), lin_utils.getOS(), lin_utils.getArchitecture(), lin_utils.getMachineType(), cpu.__dict__, lin_utils.getMemory(), lin_utils.getDiskPartitions(), lin_utils.getLBTS())
            net_config = classes.NetConfig(lin_utils.getDNS(), lin_utils.getIFAddresses())
            config = classes.Config(uid,groupid,updint, hw_config.__dict__, net_config.__dict__, lin_packages.getSoftware()) 
        else:
            print("Not supported OS")

        return config
    except Exception as err:
        print(err)

        config = classes.Err(str(err))
        return config

def main():
    config = create()
    config_data = getcfgData()
    website = config_data['website']
    webssl = config_data['webssl']
    updint = config_data['updint']

    if 'error' in config.__dict__.keys():
        return

    output = json.dumps(config.__dict__)
    output = re.sub(r"<([a-zA-Z-_]+)?.([a-zA-Z-_]+)(\d?):(\s?)", "", output)
    output = re.sub(r">", "", output)
    makerequest.postData(webssl,website,json.loads(output))
    return updint

createConfigJson()

while True:
    getupdint=main()
    print(json.dumps({"log":"sleep "+getupdint+" minutes"}))
    time.sleep(int(getupdint)*60)