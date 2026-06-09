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
    for key in (
        "conntype",
        "host",
        "port",
        "jmxport",
        "soapport",
        "webport",
        "sslverify",
        "ssl_verify",
        "servtype",
        "appserver",
        "managed_server",
    ):
        if item.get(key):
            cred[key] = item[key]
    return cred


def _availability_module_name(srvtype):
    srvtype = str(srvtype or "").strip().lower()
    if srvtype == "wildfly":
        return "jboss"
    if srvtype == "ibmacedocker":
        return "ibmace"
    return srvtype


def _rest_availability_count(srvtype, appsrv, cred):
    module_name = _availability_module_name(srvtype)
    try:
        stat_module = importlib.import_module(
            "modules.statistics." + module_name + "." + module_name
        )
        handler = getattr(stat_module, "restAvailabilityCheck", None)
        if handler is None:
            classes.Err("rest availability unsupported type:" + str(srvtype))
            return None
        return int(handler(appsrv, cred) or 0)
    except Exception as err:
        classes.Err("rest availability error:" + str(srvtype) + "/" + str(appsrv) + ":" + str(err))
        return 0


def _availability_count(srvtype, appsrv, item):
    cred = _credentials(item)
    rest_type = str(srvtype).strip().lower()
    if str(cred.get("conntype", "jms")).strip().lower() == "rest":
        if rest_type in ("weblogic", "tomcat", "jboss", "wildfly", "ibmwas", "ibmace", "ibmacedocker"):
            return _rest_availability_count(rest_type, appsrv, cred)

    checks = statarr.avlCheck(appsrv, item.get("dockercont", ""), cred)
    command = checks.get(srvtype)
    if not command:
        classes.Err("avlCheck unsupported type:" + str(srvtype))
        return None
    return _run_avl_command(command)


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

            try:
                count = _availability_count(srvtype, appsrv, item)
                if count is None:
                    continue
                if count >= 1:
                    classes.WriteData("online", "avl_" + srvtype + "_" + appsrv + ".csv")
                else:
                    classes.WriteData("offline", "avl_" + srvtype + "_" + appsrv + ".csv")
                    _send_offline_alert(webssl, website, uid, srvtype, appsrv, item)
            except subprocess.TimeoutExpired:
                classes.Err("avlCheck timed out:" + str(srvtype) + "/" + str(appsrv))

except Exception as err:
    classes.Err("error in runappavl:" + str(err))
