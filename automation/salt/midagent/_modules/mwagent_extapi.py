import json, requests, urllib3
urllib3.disable_warnings()

def getcfgData():
    with open("/var/mwagent/config/agentConfig.json", 'r') as config_file:
        config_data=json.load(config_file)
        return config_data

def postData(webssl,website,data):
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
    try:
        res = requests.post('http'+('s' if webssl=="y" else '')+'://'+website+'/extapi', data=json.dumps(data), headers=headers)
        out=res.content.decode()
    except requests.exceptions.RequestException as ex:  
        out={"error":str(ex)}
    return out

def register_mw_appsrv(token,appcode,proj,srvdata):
    try:
        config_data = getcfgData()
        serverid = config_data['uid']
        serverssl = config_data['webssl']
        mwendpoint = config_data['website']

        payload={}
        payload["token"]=token
        payload["action"]="addappsrv"
        payload["proj"]=proj
        payload["appcode"]=appcode
        payload["payload"]=srvdata
        payload["payload"]["serverid"]=serverid

        out=postData(serverssl,mwendpoint,payload)
    except Exception as err:
        out={"error": err}

    return out
