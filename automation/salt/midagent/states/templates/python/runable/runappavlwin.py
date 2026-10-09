import inspect
import importlib
import json
import os
import subprocess
import sys
from datetime import datetime

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import classes, configs, makerequest, statarr
from modules.statistics import common

AVL_TIMEOUT_SECONDS = int(os.environ.get("MIDLEO_AVL_TIMEOUT_SECONDS", "20"))

now = datetime.now()
current_time = now.strftime("%Y-%m-%d %H:%M:%S")

def _availability_count(srvtype, appsrv, item):
    return common.availability_count(srvtype, appsrv, item, AVL_TIMEOUT_SECONDS, windows=True)

def _send_offline_alert(webssl, website, uid, srvtype, appsrv, item):
    if "monid" not in item:
        return
    req = {
        "appsrv": appsrv,
        "monid": item["monid"],
        "srvid": uid,
        "appsrvid": item["appsrvid"] if "appsrvid" in item else "none",
        "srvtype": srvtype,
        "message": "Server not available",
        "alerttime": current_time,
    }
    makerequest.postMonAl(webssl, website, json.dumps(req))

try:
    avl_data = configs.getAvlData()
    config_data = configs.getcfgData()
    website = config_data["MWADMIN"]
    webssl = config_data["SSLENABLED"]
    uid = config_data["SRVUID"]

    for srvtype, srvinfo in avl_data.items():
        if not isinstance(srvinfo, dict):
            continue

        for appsrv, item in srvinfo.items():
            if not isinstance(item, dict) or item.get("enabled") != "yes":
                continue

            try:
                cnt = _availability_count(srvtype, appsrv, item)
                if cnt is None:
                    continue

                if cnt >= 1:
                    classes.WriteData("online", "avl_" + srvtype + "_" + appsrv + ".csv")
                else:
                    classes.WriteData("offline", "avl_" + srvtype + "_" + appsrv + ".csv")
                    _send_offline_alert(webssl, website, uid, srvtype, appsrv, item)
            except subprocess.TimeoutExpired:
                classes.Err("avlCheck timed out:" + str(srvtype) + "/" + str(appsrv))

except Exception as err:
    classes.Err("error in runappavl:" + str(err))
