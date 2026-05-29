import json
import sys
import os
import inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import decrypt, configs

SECRET_KEYS = {
    "pwd",
    "pass",
    "password",
    "srvpass",
    "cpass",
    "chlpass",
    "token",
}


def _arg(index, name):
    try:
        value = sys.argv[index]
    except IndexError:
        raise ValueError("Missing required argument: " + name)
    value = str(value).strip()
    if not value:
        raise ValueError("Empty required argument: " + name)
    return value


def _store_value(key, value):
    if key.lower() in SECRET_KEYS and value:
        return decrypt.encryptPWD(str(value))
    return value


def createOptAdvisorJson():
    srvtype = _arg(1, "SRVTYPE")
    appsrv = _arg(2, "APPSRV")
    raw_data = _arg(3, "OPTDATA")
    opt_data = configs.getOptAdvisorData()

    try:
        input_data = json.loads(raw_data) if raw_data else {}
    except Exception:
        raise ValueError("Invalid JSON for optadvisor configuration")

    if not isinstance(input_data, dict):
        raise ValueError("Optadvisor configuration must be a JSON object")

    if srvtype not in opt_data or not isinstance(opt_data.get(srvtype), dict):
        opt_data[srvtype] = {}

    if appsrv not in opt_data[srvtype] or not isinstance(opt_data[srvtype].get(appsrv), dict):
        opt_data[srvtype][appsrv] = {}

    opt_data[srvtype][appsrv]["optadvisor"] = True
    opt_data[srvtype][appsrv]["optadvisor_enabled"] = True
    opt_data[srvtype][appsrv]["optadvisor_only"] = True
    opt_data[srvtype][appsrv].setdefault("optadvisor_technology", srvtype)
    opt_data[srvtype][appsrv].setdefault("appserver", appsrv)

    for key, value in input_data.items():
        store_key = "pwd" if str(key).lower() == "pass" and "pwd" not in input_data else str(key)
        opt_data[srvtype][appsrv][store_key] = _store_value(store_key, value)

    appsrvid = str(opt_data[srvtype][appsrv].get("appsrvid", "")).strip()
    if appsrvid and appsrvid.lower() != "none" and not opt_data[srvtype][appsrv].get("server_id"):
        opt_data[srvtype][appsrv]["server_id"] = appsrvid

    configs.saveOptAdvisorData(opt_data)
    print(appsrv + " optadvisor configuration of type " + srvtype + " have been added")


if __name__ == "__main__":
    createOptAdvisorJson()
