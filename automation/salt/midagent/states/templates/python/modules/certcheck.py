import subprocess,json,os
from modules import classes,decrypt

def Run(uid):
  try:
    data = []
    with open(os.getcwd()+"/config/certs.json", 'r') as cert_file:
      certlist=json.load(cert_file)
    for attr, value in certlist.items():
       cpass=decrypt.decryptit(value['cpass'],uid)
       if(os.path.isfile(value['cfile'])):
         if(value['command']=="keytool"):
           certcn = subprocess.check_output("keytool -list -v -keystore "+value['cfile']+" -storepass "+cpass+" -alias "+value['clabel']+" | grep 'Owner' | cut -d '=' -f2 | cut -d ',' -f1", shell=True).strip().decode("utf-8").replace('  ','')
           certvalid = subprocess.check_output("keytool -list -v -keystore "+value['cfile']+" -storepass "+cpass+" -alias "+value['clabel']+" | grep 'until' | sed -n -e 's/^.*until: //p'", shell=True).strip().decode("utf-8")
         if(value['command']=="runmqakm"):
           certcn = subprocess.check_output("runmqakm -cert -details -db "+value['cfile']+" -label "+value['clabel']+" -stashed | grep 'CN' | grep 'Subject' | sed -n -e 's/^.*CN=//p'", shell=True).strip().decode("utf-8")
           certvalid = subprocess.check_output("runmqakm -cert -details -db "+value['cfile']+" -label "+value['clabel']+" -stashed | grep 'Not After' | sed -n -e 's/^.*: //p'", shell=True).strip().decode("utf-8")
         if bool(certcn):
           certdetails={"CN":value['clabel'],"VALID":certvalid,"FILE":value['cfile']}
           data.append(json.loads(json.dumps(certdetails)))
    return data
  except Exception as err:
    classes.Err("Exception:"+str(err)+" at checkcert()")
    return None