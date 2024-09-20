import json,sys,os,inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir) 

from modules.base import decrypt,configs

CERTDATA=sys.argv[1]

print(CERTDATA)
def createCertJson():
   config_data = configs.getcfgData()
   uid = config_data['SRVUID']

   if not uid:
      pass

   try:
      CERTINP=json.loads(CERTDATA)
   except Exception as err:
      CERTINP={}

   try:
      cert_data = configs.getcertData()
   except Exception as err:
      cert_data = {}

   cert_data[CERTINP["label"]] = {
      "command": CERTINP["tool"],
      "cfile": CERTINP["keystore"],
      "clabel": CERTINP["label"],
      "cpass": decrypt.encrypt(CERTINP["password"],uid+uid+uid+uid)
   }

   with open(os.getcwd()+"/config/certs.json", 'w+') as cert_file:
      json.dump(cert_data, cert_file)
   print(CERTINP["label"]+" configuration added")
    
if __name__ == "__main__":
   createCertJson()