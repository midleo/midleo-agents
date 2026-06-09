import json
import sys
import os
import inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import decrypt, configs


def _arg(index, name):
    try:
        value = sys.argv[index]
    except IndexError:
        raise ValueError("Missing required argument: " + name)
    value = str(value).strip()
    if not value:
        raise ValueError("Empty required argument: " + name)
    return value


def createMonJson():
    srvtype = _arg(1, "SRVTYPE")
    appsrv = _arg(2, "APPSRV")
    stdata = _arg(3, "STDATA")
    mon_data = configs.getmonData()

    try:
        stjsdata = json.loads(stdata) if stdata else {}
    except Exception:
        raise ValueError("Invalid JSON for appstat configuration")

    if not isinstance(stjsdata, dict):
        raise ValueError("Appstat configuration must be a JSON object")

    if srvtype not in mon_data or not isinstance(mon_data.get(srvtype), dict):
        mon_data[srvtype] = {}

    if appsrv not in mon_data[srvtype] or not isinstance(mon_data[srvtype].get(appsrv), dict):
        mon_data[srvtype][appsrv] = {}

    if "pass" in stjsdata and "pwd" not in stjsdata:
        stjsdata["pwd"] = stjsdata.pop("pass")
    if "conntype" not in stjsdata:
        stjsdata["conntype"] = "jms"

    for k, item in stjsdata.items():
        mon_data[srvtype][appsrv][k] = decrypt.encryptPWD(item) if k == "pwd" and item else item

    configs.savemonData(mon_data)
    print(appsrv + " of type " + srvtype + " have been added")


if __name__ == "__main__":
    createMonJson()
