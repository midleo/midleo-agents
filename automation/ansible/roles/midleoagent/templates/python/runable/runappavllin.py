import json,subprocess,sys,os,inspect
from datetime import datetime

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir) 

from modules.base import makerequest,classes,configs,statarr

try:
    from subprocess import CompletedProcess
    from subprocess import run as sp_run
except:
    class CompletedProcess:
        _custom_impl = True

        def __init__(self, args, returncode, stdout=None, stderr=None):
            self.args = args
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

        def check_returncode(self):
            if self.returncode != 0:
                err = subprocess.CalledProcessError(self.returncode,
                                                    self.args,
                                                    output=self.stdout)
                raise err
            return self.returncode

    def sp_run(*popenargs, **kwargs):
        this_input = kwargs.pop("input", None)
        check = kwargs.pop("handle", False)

        if this_input is not None:
            if 'stdin' in kwargs:
                raise ValueError('stdin and input arguments may not '
                                 'both be used.')
            kwargs['stdin'] = subprocess.PIPE

        process = subprocess.Popen(*popenargs, **kwargs)
        try:
            outs, errs = process.communicate(this_input)
        except Exception as ex:
            process.kill()
            process.wait()
            raise ex
        returncode = process.poll()
        if check and returncode:
            raise subprocess.CalledProcessError(returncode, popenargs,
                                                output=outs)
        return CompletedProcess(popenargs, returncode, stdout=outs,
                                stderr=errs)
    subprocess.run = sp_run

now = datetime.now()
current_time = now.strftime("%Y-%m-%d %H:%M:%S")

try:
   avl_data = configs.getAvlData()
   config_data = configs.getcfgData()
   website = config_data['MWADMIN']
   webssl = config_data['SSLENABLED']
   inttoken = config_data['INTTOKEN']
   uid = config_data['SRVUID']
   if len(avl_data)>0:
    for srvtype,srvinfo in avl_data.items():
      if len(srvinfo.items())>0: 
        for k,item in srvinfo.items():
          cred = {}

          if("usr" in item and item["usr"] != ""):
            cred["usr"] = item["usr"]
          if("pwd" in item and item["pwd"] != ""):
            cred["pwd"] = item["pwd"]
          if("mngmport" in item and item["mngmport"] != ""):
            cred["mngmport"] = item["mngmport"]

          if("dockercont" in item):
            ret=statarr.avlCheck(k,item["dockercont"],cred)
          else:
            ret=statarr.avlCheck(k,"",cred)
          if(item["enabled"]=='yes'):
            ret=ret[srvtype]
            try:
             output = sp_run(ret,shell=True,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
             output = output.stdout.decode()
             if(int(output)>=1):
               classes.WriteData("online","avl_"+srvtype+"_"+k+".csv")
             else:
               classes.WriteData("offline","avl_"+srvtype+"_"+k+".csv")
               if("monid" in item):
                  req={}
                  req["appsrv"]=k
                  req["monid"]=item["monid"]
                  req["srvid"]=uid
                  req["srvtype"]=srvtype
                  req["message"]="Server not available"
                  req["alerttime"]=current_time
                  req["inttoken"]=inttoken
                  makerequest.postMonAl(webssl,website,json.dumps(req))
            except subprocess.CalledProcessError as e:
             classes.Err("avlCheck err:"+str(e.output))
except Exception as err:
   classes.Err("error in runappavl:"+str(err)) 
