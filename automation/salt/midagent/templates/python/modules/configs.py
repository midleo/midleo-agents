import json, os
from modules import classes


def getcfgData():
    with open(os.getcwd()+"/config/agentConfig.json", 'r') as config_file:
        config_data=json.load(config_file)
        return config_data
    
def getmonData():
   with open(os.getcwd()+"/config/confmon.json", 'r') as mon_file:
      mon_data=json.load(mon_file)
      return mon_data
