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
