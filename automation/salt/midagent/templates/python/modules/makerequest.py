import requests, json, base64, urllib3
from modules import classes
urllib3.disable_warnings()

def postData(webssl,website,data):
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
    try:
        res = requests.post('http'+('s' if webssl=="y" else '')+'://'+website+'/pubapi/updatesrv', data=json.dumps(data), headers=headers)
        classes.Err("HTTPResponse:"+res.content.decode())
    except requests.exceptions.RequestException as ex:  
        classes.Err("Exception:"+str(ex))

def postQData(webssl,website,qm,q,data):
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
    try:
        res = requests.post('http'+('s' if webssl=="y" else '')+'://'+website+'/pubapi/updateqstat/'+qm+'/'+q, data=json.dumps(data), headers=headers)
        classes.Err("postQdata HTTPResponse:"+res.content.decode())
    except requests.exceptions.RequestException as ex:  
        classes.Err("Exception:"+str(ex))

def getQStat(webssl,website,webport,qmgr,queue,usr,passwd):
    headers = {'Content-Type': 'text/plain', 'charset':'utf-8'}
    try:
        res = requests.get('http'+('s' if webssl=="y" else '')+'://'+website+':'+webport+'/ibmmq/rest/v1/admin/qmgr/'+qmgr+'/queue/'+queue+'?attributes=storage.maximumDepth&status=status.currentDepth,status.oldestMessageAge,status.uncommittedMessages,status.lastGet,status.lastPut', verify=False, headers=headers, auth=(usr, base64.b64decode(passwd).decode('utf-8').rstrip()))
        if 200 == res.status_code :
          return res.json()
        else:
          return '{}'
    except requests.exceptions.RequestException as ex:  
        classes.Err("Exception:"+str(ex))