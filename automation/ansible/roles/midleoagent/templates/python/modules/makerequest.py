import requests, json, os

def postData(webssl,website,data):
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
    logfile = open(os.getcwd()+"/logs/midleoagent.log", 'a')
    try:
        res = requests.post('http'+('s' if webssl=="y" else '')+'://'+website+'/pubapi/updatesrv', data=json.dumps(data), headers=headers)
        logfile.write(res.content.decode()+ "\n")
    except requests.exceptions.RequestException as e:  
        logfile.write(e+ "\n")
    logfile.close()