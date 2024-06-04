import json, os, uuid

def getcfgData():
    with open(os.getcwd()+"/config/agentConfig.json", 'r') as config_file:
        config_data=json.load(config_file)
        return config_data
   
def getmonData():
   with open(os.getcwd()+"/config/confmon.json", 'r') as mon_file:
      mon_data=json.load(mon_file)
      return mon_data

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

        with open(os.getcwd()+"/config/agentConfig.json", 'w+') as config_file:
            json.dump(config_data, config_file)

def getcertData():
   with open(os.getcwd()+"/config/certs.json", 'r') as cert_file:
      cert_data=json.load(cert_file)
      return cert_data
   
def getstatData():
    with open(os.getcwd()+"/config/statlist.json", 'r') as stat_file:
      stat_data=json.load(stat_file)
      return stat_data
    
def gettrackData():
   with open(os.getcwd()+"/config/conftrack.json", 'r') as track_file:
      track_data=json.load(track_file)
      return track_data
   
def getAvlData():
   with open(os.getcwd()+"/config/confavl.json", 'r') as avl_file:
      avl_data=json.load(avl_file)
      return avl_data