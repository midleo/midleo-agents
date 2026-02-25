import json,subprocess,sys,os,inspect,glob
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
   config_data = configs.getcfgData()
   website = config_data['MWADMIN']
   webssl = config_data['SSLENABLED']
   inttoken = config_data['INTTOKEN']
   uid = config_data['SRVUID']
   log_dir = os.path.join(parentdir, "extchecks")
   log_files = glob.glob(os.path.join(log_dir, "*.log"))
   if log_files:
      for log_file in log_files:
          data = []
          with open(log_file, "r") as f:
            for line in f:
              line = line.strip()
              if not line:
                continue

              parts = line.split(maxsplit=3) 
              if len(parts) < 4:
                continue
              obj_parts = parts[1].split("_", 2)
              if len(obj_parts) < 3:
                continue
              srvtype, appsrv, objname_only = obj_parts

              entry = {
                "code": parts[0],
                "srvtype": srvtype,
                "appsrv": appsrv,
                "objname": objname_only,
                "interval": parts[2],
                "text": parts[3],
                "alerttime": current_time,
                "source": os.path.basename(log_file)
              }
              data.append(entry)
          if data:
             payload = {
               "inttoken": inttoken,
               "srvid": uid,
               "data": data
             }
             makerequest.postMonCheck(webssl,website,json.dumps(payload))

except Exception as err:
   classes.Err("error in getextmonchecks:"+str(err)) 
