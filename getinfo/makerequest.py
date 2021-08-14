import requests
import json

def postData(webssl,website,data):
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
    try:
        res = requests.post('http'+('s' if webssl=="y" else '')+'://'+website+'/pubapi/updatesrv', data=json.dumps(data), headers=headers)
        print(res.content.decode())
    except requests.exceptions.RequestException as e:  
        print(e)