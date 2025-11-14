import requests, json, base64, urllib3
from midleo_client import AGENT_VER
from modules.base import classes
urllib3.disable_warnings()

def postData(webssl,website,data):
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain', 'User-Agent': 'MWAdmin v.'+AGENT_VER}
    try:
        res = requests.post('http'+('s' if webssl=="y" else '')+'://'+website+'/pubapi/updatesrv', data=json.dumps(data), headers=headers, verify=False)
        classes.Err("HTTPResponse:"+res.content.decode())
    except requests.exceptions.RequestException as ex:  
        classes.Err("Exception:"+str(ex))

def postStatData(webssl,website,thisdata):
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain', 'User-Agent': 'MWAdmin v.'+AGENT_VER}
    try:
        res = requests.post('http'+('s' if webssl=="y" else '')+'://'+website+'/pubapi/updatestat', data=thisdata, headers=headers, verify=False)
        classes.Err("HTTPResponse:"+res.content.decode())
    except requests.exceptions.RequestException as ex:  
        classes.Err("Exception:"+str(ex))

def postibmmqQData(webssl,website,qm,data):
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain', 'User-Agent': 'MWAdmin v.'+AGENT_VER}
    try:
        res = requests.post('http'+('s' if webssl=="y" else '')+'://'+website+'/pubapi/updateibmmqqstat/'+qm, data=data, headers=headers, verify=False)
        classes.Err("postibmmqQData HTTPResponse:"+res.content.decode())
    except requests.exceptions.RequestException as ex:  
        classes.Err("Exception:"+str(ex))

def postibmmqCHData(webssl,website,qm,data):
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain', 'User-Agent': 'MWAdmin v.'+AGENT_VER}
    try:
        res = requests.post('http'+('s' if webssl=="y" else '')+'://'+website+'/pubapi/updateibmmqchstat/'+qm, data=data, headers=headers, verify=False)
        classes.Err("postibmmqCHdata HTTPResponse:"+res.content.decode())
    except requests.exceptions.RequestException as ex:  
        classes.Err("Exception:"+str(ex))

def getQRestStat(webssl,website,webport,qmgr,queue,usr,passwd):
    headers = {'Content-Type': 'text/plain', 'charset':'utf-8', 'User-Agent': 'MWAdmin v.'+AGENT_VER}
    try:
        res = requests.get('http'+('s' if webssl=="y" else '')+'://'+website+':'+webport+'/ibmmq/rest/v1/admin/qmgr/'+qmgr+'/queue/'+queue+'?type=local&attributes=storage.maximumDepth&status=status', verify=False, headers=headers, auth=(usr, base64.b64decode(passwd).decode('utf-8').rstrip()))
        if 200 == res.status_code :
          return res.json()
        else:
          return '{}'
    except requests.exceptions.RequestException as ex:  
        classes.Err("Exception:"+str(ex))

def postTrackData(webssl,website,thisdata):
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain', 'User-Agent': 'MWAdmin v.'+AGENT_VER}
    try:
        res = requests.post('http'+('s' if webssl=="y" else '')+'://'+website+'/pubapi/updateibmqtrack', data=thisdata, headers=headers, verify=False)
        classes.Err("HTTPResponse:"+res.content.decode())
    except requests.exceptions.RequestException as ex:  
        classes.Err("Exception:"+str(ex))

def postAvlData(webssl,website,thisdata):
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain', 'User-Agent': 'MWAdmin v.'+AGENT_VER}
    try:
        res = requests.post('http'+('s' if webssl=="y" else '')+'://'+website+'/pubapi/updateappsrvavl', data=thisdata, headers=headers, verify=False)
        classes.Err("HTTPResponse:"+res.content.decode())
    except requests.exceptions.RequestException as ex:  
        classes.Err("Exception:"+str(ex))

def postMonAl(webssl,website,thisdata):
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain', 'User-Agent': 'MWAdmin v.'+AGENT_VER}
    try:
        res = requests.post('http'+('s' if webssl=="y" else '')+'://'+website+'/pubapi/monalert', data=thisdata, headers=headers, verify=False)
        classes.Err("HTTPResponse:"+res.content.decode())
    except requests.exceptions.RequestException as ex:  
        classes.Err("Exception:"+str(ex))

def postMonCheck(webssl,website,thisdata):
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain', 'User-Agent': 'MWAdmin v.'+AGENT_VER}
    try:
        res = requests.post('http'+('s' if webssl=="y" else '')+'://'+website+'/pubapi/extmoncheck', data=thisdata, headers=headers, verify=False)
        classes.Err("HTTPResponse:"+res.content.decode())
    except requests.exceptions.RequestException as ex:  
        classes.Err("Exception:"+str(ex))