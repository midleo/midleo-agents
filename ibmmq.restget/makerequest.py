import requests
import json

def getQStat(webssl,website,qmgr,usr,passwd):
    headers = {'Content-Type': 'text/plain', 'charset':'utf-8'}
    try:
        res = requests.get('http'+('s' if webssl=="y" else '')+'://'+website+'/ibmmq/rest/v1/admin/qmgr/'+qmgr+'/queue?type=local&attributes=storage.maximumDepth&status=status.currentDepth,status.oldestMessageAge,status.uncommittedMessages,status.lastGet,status.lastPut&filter=status.currentDepth:greaterThan:0', headers=headers, auth=(usr, passwd))
        return res.json()
    except requests.exceptions.RequestException as e:  
        print(e)

def getCHStat(webssl,website,qmgr,usr,passwd):
    headers = {'Content-Type': 'text/plain', 'charset':'utf-8'}
    try:
        res = requests.get('http'+('s' if webssl=="y" else '')+'://'+website+'/ibmmq/rest/v1/admin/qmgr/'+qmgr+'/channel?type=all&status=currentStatus.extended&filter=currentStatus.state:equalTo:running', headers=headers, auth=(usr, passwd))
        return res.json()
    except requests.exceptions.RequestException as e:  
        print(e)