import inspect
import json
import os
import subprocess
import sys
from datetime import datetime

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import classes, configs, makerequest, statarr

AVL_TIMEOUT_SECONDS = int(
    os.environ.get(
        "MIDLEO_AVL_TIMEOUT_SECONDS", os.environ.get("JOB_TIMEOUT_SECONDS", "55")
    )
)

now = datetime.now()
current_time = now.strftime("%Y-%m-%d %H:%M:%S")


def _credentials(item):
    cred = {}
    if item.get("usr"):
        cred["usr"] = item["usr"]
    if item.get("pwd"):
        cred["pwd"] = item["pwd"]
    if item.get("mngmport"):
        cred["mngmport"] = item["mngmport"]
    if item.get("ssl"):
        cred["ssl"] = item["ssl"]
    return cred


def _run_avl_command(command):
    proc = subprocess.run(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=AVL_TIMEOUT_SECONDS,
        check=False,
    )
    output = proc.stdout.decode(errors="ignore").strip()
    try:
        return int(output or "0")
    except ValueError:
        classes.Err("avlCheck unexpected output:" + output[:500])
        return 0


def _send_offline_alert(webssl, website, uid, srvtype, appsrv, item):
    if "monid" not in item:
        return
    req = {
        "appsrv": appsrv,
        "monid": item["monid"],
        "appsrvid": item["appsrvid"] if "appsrvid" in item else "none",
        "srvid": uid,
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

            checks = statarr.avlCheck(appsrv, item.get("dockercont", ""), _credentials(item))
            command = checks.get(srvtype)
            if not command:
                classes.Err("avlCheck unsupported type:" + str(srvtype))
                continue

            try:
                count = _run_avl_command(command)
                if count >= 1:
                    classes.WriteData("online", "avl_" + srvtype + "_" + appsrv + ".csv")
                else:
                    classes.WriteData("offline", "avl_" + srvtype + "_" + appsrv + ".csv")
                    _send_offline_alert(webssl, website, uid, srvtype, appsrv, item)
            except subprocess.TimeoutExpired:
                classes.Err("avlCheck timed out:" + str(srvtype) + "/" + str(appsrv))

except Exception as err:
    classes.Err("error in runappavl:" + str(err))
