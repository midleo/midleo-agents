import platform
import makerequest
import json
import re
import time
import requests
import json
from cryptography.fernet import Fernet

if (platform.system()!="Linux" and platform.system()!="Windows"):
    print('Not supported OS')
    quit()
    
def getcfgData():
    with open('./agentConfig.json', 'r') as config_file:
        data=json.load(config_file)
        config_data = {}
        config_data['pwd']=str.encode(data['pwd'])
        key=str.encode(data['pwdhash'])
        f = Fernet(key)
        config_data['pwd']=f.decrypt(config_data['pwd']).decode("utf-8")
        config_data['userid']=data['userid']
        config_data['website']=data['website']
        config_data['webssl']=data['webssl']
        
        config_data['updint']=data['updint']
        config_data['qmgr']=data['qmgr']
        return config_data

def createConfigJson():
    try:
        config_data = getcfgData()
    except Exception as err:

        config_data = {
            "website": input("Please provide IBM MQ REST server(localhost?):"),
            "webssl": input("SSL enabled ? (y/n):"),
            "userid": input("Please provide username for REST access:"),
            "qmgr": input("comma separated IBM MQ qmanagers:"),
            "pwd": input("Please provide password for REST access:"),
            "updint": input("Update interval (in minutes):")
        }

        key = Fernet.generate_key()
        config_data["pwdhash"]=key.decode("utf-8")
        f = Fernet(key)
        pwd=config_data["pwd"].encode()
        config_data["pwd"]=f.encrypt(pwd).decode("utf-8")
        with open('./agentConfig.json', 'w+') as config_file:
            json.dump(config_data, config_file, indent=4, sort_keys=True)

def main():
    config_data = getcfgData()
    pwd = config_data['pwd']
    website = config_data['website']
    webssl = config_data['webssl']
    updint = config_data['updint']
    userid = config_data['userid']
    
    qmgr = config_data['qmgr']
    qmgrlist = qmgr.split(",")
    #get Queue status
    for x in range(len(qmgrlist)): 
        qinfo=makerequest.getQStat(webssl,website,qmgrlist[x],userid,pwd)
        print(qinfo)
    
    #get Channel status
    for x in range(len(qmgrlist)): 
        qinfo=makerequest.getCHStat(webssl,website,qmgrlist[x],userid,pwd)
        print(qinfo)
        
    return updint

createConfigJson()

while True:
    getupdint=main()
    print(json.dumps({"log":"sleep "+getupdint+" minutes"}))
    time.sleep(int(getupdint)*60)