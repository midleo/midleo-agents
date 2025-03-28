import json,subprocess,sys,os,inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir) 

from modules.base import makerequest,classes,configs

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

AMQSEVT=os.environ['AMQSEVT']

try:
   avl_data = configs.getAvlData()
   config_data = configs.getcfgData()
   website = config_data['MWADMIN']
   webssl = config_data['SSLENABLED']
   inttoken = config_data['INTTOKEN']
   uid = config_data['SRVUID']


   if len(avl_data)>0:
    for srvtype,srvinfo in avl_data.items():
     if len(srvinfo.items()) > 0 and (srvtype == "ibmmq" or srvtype == "ibmmqdocker"):
        for k,item in srvinfo.items():
          try:
            if srvtype == "ibmmqdocker":
              container=item["dockercont"]
              thisscript=AMQSEVT+" -m "+k+" -q SYSTEM.ADMIN.PERFM.EVENT -w 1 -o json | jq . -c --slurp"
              command = ["docker", "exec", container, "bash", "-c", thisscript]
              output = subprocess.run(command, capture_output=True, text=True)
              output = output.stdout
            else:
              output = sp_run("sudo su - mqm -c '"+AMQSEVT+" -m "+k+" -q SYSTEM.ADMIN.PERFM.EVENT -w 1 -o json | jq . -c --slurp'",shell=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
              output = output.stdout.decode() 
            try:
               out = json.loads(output)
               if len(out)>0:
                  for event in out:
                     eventData = event["eventData"]
                     if eventData["baseObjectName"]!="SYSTEM.ADMIN.PERFM.EVENT":
                        event_table = "\n"
                        for key, val in eventData.items():
                           event_table += f"{key}: {val}\n"
                        ret={}
                        ret["appsrv"]=eventData["queueMgrName"]
                        ret["monid"]="MQRC" + str(event["eventReason"]["value"])
                        ret["srvid"]=uid
                        ret["srvtype"]=srvtype
                        ret["alerttime"]=event["eventCreation"]["timeStamp"]
                        ret["message"]=event["eventReason"]["name"]+event_table
                        ret["inttoken"]=inttoken
                        ret["object"]=eventData["baseObjectName"]
                        makerequest.postMonAl(webssl,website,json.dumps(ret))

            except:
               classes.Err("Return error:"+output)
          except subprocess.CalledProcessError as e:
            classes.Err("amqsevt err:"+e.output)
   
except Exception as err:
   classes.Err("No such configuration file - config/conftrack.json."+err) 
