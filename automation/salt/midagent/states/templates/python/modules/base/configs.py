import json, os, uuid

def getcfgData():
    try:
       with open(os.getcwd()+"/config/agentConfig.json", 'r') as config_file:
          config_data=json.load(config_file)
    except:
      config_data={}      
    return config_data
   
def getmonData():
   try:
      with open(os.getcwd()+"/config/confapplstat.json", 'r') as mon_file:
         mon_data=json.load(mon_file)
   except:
      mon_data={}
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
            "updint": input("Update interval (in minutes):"),
            "inttoken": input("Internal API Token:")
        }

        with open(os.getcwd()+"/config/agentConfig.json", 'w+') as config_file:
            json.dump(config_data, config_file)

def getcertData():
   try:
      with open(os.getcwd()+"/config/certs.json", 'r') as cert_file:
         cert_data=json.load(cert_file)
   except:
      cert_data={}
   return cert_data
    
def gettrackData():
   try:
      with open(os.getcwd()+"/config/conftrack.json", 'r') as track_file:
         track_data=json.load(track_file)
   except:
      track_data={}
   return track_data
   
def getAvlData():
   try:
      with open(os.getcwd()+"/config/confavl.json", 'r') as avl_file:
         avl_data=json.load(avl_file)
   except:
      avl_data={}
   return avl_data