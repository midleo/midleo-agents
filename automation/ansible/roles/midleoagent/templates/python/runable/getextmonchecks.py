import json, subprocess, sys, os, inspect, glob, re
from datetime import datetime

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import makerequest, classes, configs, statarr

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
                err = subprocess.CalledProcessError(
                    self.returncode,
                    self.args,
                    output=self.stdout
                )
                raise err
            return self.returncode

    def sp_run(*popenargs, **kwargs):
        this_input = kwargs.pop("input", None)
        check = kwargs.pop("check", False)

        if this_input is not None:
            if "stdin" in kwargs:
                raise ValueError("stdin and input arguments may not both be used.")
            kwargs["stdin"] = subprocess.PIPE

        process = subprocess.Popen(*popenargs, **kwargs)
        try:
            outs, errs = process.communicate(this_input)
        except Exception as ex:
            process.kill()
            process.wait()
            raise ex

        returncode = process.poll()
        if check and returncode:
            raise subprocess.CalledProcessError(returncode, popenargs, output=outs)

        return CompletedProcess(popenargs, returncode, stdout=outs, stderr=errs)

    subprocess.run = sp_run

now = datetime.now()
current_time = now.strftime("%Y-%m-%d %H:%M:%S")

line_pattern = re.compile(r'^([^{\s]+)\{(.*)\}\s+(-?\d+)\s*$')
kv_pattern = re.compile(r'([A-Za-z0-9_\-]+)\s*=\s*"((?:\\"|[^"])*)"')

def parse_attrs(attr_text):
    attrs = {}
    for key, value in kv_pattern.findall(attr_text):
        attrs[key] = value.replace('\\"', '"')
    return attrs

try:
    config_data = configs.getcfgData()
    website = config_data["MWADMIN"]
    webssl = config_data["SSLENABLED"]
    inttoken = config_data["INTTOKEN"]
    uid = config_data["SRVUID"]

    mdl_dir = os.path.join(parentdir, "extchecks")
    mdl_files = glob.glob(os.path.join(mdl_dir, "*.mdl"))

    if mdl_files:
        for mdl_file in mdl_files:
            data = []

            with open(mdl_file, "r") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line:
                        continue

                    match = line_pattern.match(line)
                    if not match:
                        continue

                    obj_full = match.group(1)
                    attr_text = match.group(2)
                    code = match.group(3)

                    obj_parts = obj_full.split("_", 2)
                    if len(obj_parts) < 3:
                        continue

                    srvtype, appsrv, objname_only = obj_parts
                    attrs = parse_attrs(attr_text)
                    interval = attrs.get("interval", "0")

                    entry = {
                        "code": code,
                        "srvtype": srvtype,
                        "appsrv": appsrv,
                        "objname": objname_only,
                        "interval": interval,
                        "alerttime": current_time,
                        "source": os.path.basename(mdl_file)
                    }
                    if "interval" in attrs:
                        del attrs["interval"]
                        
                    for k, v in attrs.items():
                        entry[k] = v

                    data.append(entry)

            if data:
                payload = {
                    "inttoken": inttoken,
                    "srvid": uid,
                    "data": data
                }
                makerequest.postMonCheck(webssl, website, json.dumps(payload))

except Exception as err:
    classes.Err("error in getextmonchecks:" + str(err))