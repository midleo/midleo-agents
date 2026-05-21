import json
import os
import requests
import urllib3


CONFIG_PATHS = (
    "/var/midleoagent/config/mwagent.config",
    "/var/mwagent/config/agentConfig.json",
)


def _parse_key_value_config(path):
    data = {}
    with open(path, "r", encoding="utf-8") as config_file:
        for line in config_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def _normalize_config(data):
    if "SRVUID" not in data:
        return data

    return {
        "uid": data.get("SRVUID", ""),
        "webssl": data.get("SSLENABLED", "n"),
        "website": data.get("MWADMIN", ""),
        "sslverify": data.get("SSLVERIFY", "y"),
    }


def getcfgData():
    for path in CONFIG_PATHS:
        if not os.path.isfile(path):
            continue

        if path.endswith(".json"):
            with open(path, "r", encoding="utf-8") as config_file:
                return _normalize_config(json.load(config_file))

        return _normalize_config(_parse_key_value_config(path))

    raise FileNotFoundError("No Midleo agent config found")

def postData(webssl,website,data,sslverify=True):
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
    if not sslverify:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    website = str(website or "").strip().rstrip("/")
    if website.startswith("http://") or website.startswith("https://"):
        url = website + "/extapi"
    else:
        url = 'http'+('s' if webssl=="y" else '')+'://'+website+'/extapi'
    try:
        res = requests.post(
            url,
            data=json.dumps(data),
            headers=headers,
            verify=sslverify,
            timeout=20,
        )
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
        sslverify = str(config_data.get('sslverify', 'y')).lower() not in ('n', 'no', 'false', '0')

        payload={}
        payload["token"]=token
        payload["action"]="addappsrv"
        payload["proj"]=proj
        payload["appcode"]=appcode
        payload["payload"]=srvdata
        payload["payload"]["serverid"]=serverid

        out=postData(serverssl,mwendpoint,payload,sslverify)
    except Exception as err:
        out={"error": str(err)}

    return out
