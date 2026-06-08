import glob
import inspect
import json
import os
import re
import sys
from datetime import datetime

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import classes, configs, makerequest

MAX_MDL_BYTES = 1024 * 1024

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
    uid = config_data["SRVUID"]

    mdl_dir = os.path.join(parentdir, "extchecks")
    mdl_files = glob.glob(os.path.join(mdl_dir, "*.mdl"))

    for mdl_file in mdl_files:
        if os.path.getsize(mdl_file) > MAX_MDL_BYTES:
            classes.Err("Skipping oversized extcheck file:" + os.path.basename(mdl_file))
            continue

        data = []
        with open(mdl_file, "r", encoding="utf-8", errors="replace") as file_handle:
            for raw_line in file_handle:
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
                interval = attrs.pop("interval", "0")

                entry = {
                    "code": code,
                    "srvtype": srvtype,
                    "appsrv": appsrv,
                    "objname": objname_only,
                    "interval": interval,
                    "alerttime": current_time,
                    "source": os.path.basename(mdl_file),
                }
                entry.update(attrs)
                data.append(entry)

        if data:
            payload = {
                    "srvid": uid,
                "data": data,
            }
            makerequest.postMonCheck(webssl, website, json.dumps(payload))

except Exception as err:
    classes.Err("error in getextmonchecks:" + str(err))
