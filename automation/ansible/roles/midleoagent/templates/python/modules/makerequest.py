import requests, json
from modules import classes

def postData(webssl,website,data):
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
    try:
        res = requests.post('http'+('s' if webssl=="y" else '')+'://'+website+'/pubapi/updatesrv', data=json.dumps(data), headers=headers)
        classes.Err("HTTPResponse:"+res.content.decode())
    except requests.exceptions.RequestException as ex:  
        classes.Err("Exception:"+str(ex))
