import requests, json, base64, urllib3, subprocess, os
from modules import classes
urllib3.disable_warnings()

def postData(webssl,website,data):
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
    try:
        res = requests.post('http'+('s' if webssl=="y" else '')+'://'+website+'/pubapi/updatesrv', data=json.dumps(data), headers=headers, verify=False)
        classes.Err("HTTPResponse:"+res.content.decode())
    except requests.exceptions.RequestException as ex:  
        classes.Err("Exception:"+str(ex))

def postStatData(webssl,website,thisdata):
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
    try:
        res = requests.post('http'+('s' if webssl=="y" else '')+'://'+website+'/pubapi/updatestat', data=thisdata, headers=headers, verify=False)
        classes.Err("HTTPResponse:"+res.content.decode())
    except requests.exceptions.RequestException as ex:  
        classes.Err("Exception:"+str(ex))

def postQData(webssl,website,qm,q,data):
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
    try:
        res = requests.post('http'+('s' if webssl=="y" else '')+'://'+website+'/pubapi/updateqstat/'+qm+'/'+q, data=json.dumps(data), headers=headers, verify=False)
        classes.Err("postQdata HTTPResponse:"+res.content.decode())
    except requests.exceptions.RequestException as ex:  
        classes.Err("Exception:"+str(ex))

def getQStat(webssl,website,webport,qmgr,queue,usr,passwd):
    headers = {'Content-Type': 'text/plain', 'charset':'utf-8'}
    try:
        res = requests.get('http'+('s' if webssl=="y" else '')+'://'+website+':'+webport+'/ibmmq/rest/v1/admin/qmgr/'+qmgr+'/queue/'+queue+'?type=local&attributes=storage.maximumDepth&status=status', verify=False, headers=headers, auth=(usr, base64.b64decode(passwd).decode('utf-8').rstrip()))
        if 200 == res.status_code :
          return res.json()
        else:
          return '{}'
    except requests.exceptions.RequestException as ex:  
        classes.Err("Exception:"+str(ex))

def getJQstat(JAVA_OPTS,qmgr,queue,thres):
    try:
       qinfo = subprocess.check_output("java "+JAVA_OPTS+" -jar "+os.getcwd()+"/resources/midleomon.jar"+" '{\"function\":\"QSTAT\",\"qmanager\":\""+qmgr+"\",\"alertnum\":\""+thres+"\"}' \""+queue+"\"", shell=True,stderr=subprocess.STDOUT)
       return qinfo
    except subprocess.CalledProcessError as e:
       classes.Err("Exception:"+str(e.output))

def postTrackData(webssl,website,thisdata):
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
    try:
        res = requests.post('http'+('s' if webssl=="y" else '')+'://'+website+'/pubapi/updateibmqtrack', data=thisdata, headers=headers, verify=False)
        classes.Err("HTTPResponse:"+res.content.decode())
    except requests.exceptions.RequestException as ex:  
        classes.Err("Exception:"+str(ex))

def postAvlData(webssl,website,thisdata):
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
    try:
        res = requests.post('http'+('s' if webssl=="y" else '')+'://'+website+'/pubapi/updateappsrvavl', data=thisdata, headers=headers, verify=False)
        classes.Err("HTTPResponse:"+res.content.decode())
    except requests.exceptions.RequestException as ex:  
        classes.Err("Exception:"+str(ex))