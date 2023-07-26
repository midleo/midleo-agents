import subprocess,json
from modules import classes

def Run(certs):
  try:
    data = []
    command = "keytool"
    rc, out = subprocess.getstatusoutput("which "+command)
    if rc != 0:
      command = "runmqakm"
      rc, out = subprocess.getstatusoutput("which "+command)
    certlist=certs.split(";")
    for cert in certlist:
       cfile=cert.split("#")[0]
       clabel=cert.split("#")[1]
       cpass=cert.split("#")[2]
       if(command=="keytool"):
         certcn = subprocess.check_output("keytool -list -v -keystore "+cfile+" -storepass "+cpass+" -alias "+clabel+" | grep 'Owner' | grep -o -P '(?<=CN=).*(?=, OU)'", shell=True).strip().decode("utf-8").replace('  ','')
         certvalid = subprocess.check_output("keytool -list -v -keystore "+cfile+" -storepass "+cpass+" -alias "+clabel+" | grep 'until' | sed -n -e 's/^.*until: //p'", shell=True).strip().decode("utf-8")
       if(command=="runmqakm"):
         certcn = subprocess.check_output("runmqakm -cert -details -db "+cfile+" -label "+clabel+" -stashed | grep 'Owner' | grep -o -P '(?<=CN=).*(?=, OU)'", shell=True).strip().decode("utf-8")
         certvalid = subprocess.check_output("runmqakm -cert -details -db "+cfile+" -label "+clabel+" -stashed | grep 'Not After' | sed -n -e 's/^.*Not After: //p'", shell=True).strip().decode("utf-8")
       if bool(certcn):
         certdetails={"CN":certcn,"VALID":certvalid,"FILE":cfile}
         data.append(json.loads(json.dumps(certdetails)))
    return data
  except Exception as err:
    classes.Err("Exception:"+str(err)+" at checkcert()")
    return None