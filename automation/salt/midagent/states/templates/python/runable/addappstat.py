import json
import sys
import os
import inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import decrypt, configs

SRVTYPE = sys.argv[1]
APPSRV = sys.argv[2]
STDATA = sys.argv[3]


def createMonJson():
    mon_data = configs.getmonData()

    try:
        stjsdata = json.loads(STDATA) if STDATA else {}
    except Exception:
        raise ValueError("Invalid JSON for appstat configuration")

    if not isinstance(stjsdata, dict):
        raise ValueError("Appstat configuration must be a JSON object")

    if SRVTYPE not in mon_data or not isinstance(mon_data.get(SRVTYPE), dict):
        mon_data[SRVTYPE] = {}

    if APPSRV not in mon_data[SRVTYPE] or not isinstance(mon_data[SRVTYPE].get(APPSRV), dict):
        mon_data[SRVTYPE][APPSRV] = {}

    for k, item in stjsdata.items():
        mon_data[SRVTYPE][APPSRV][k] = decrypt.encryptPWD(item) if k == "pwd" and item else item

    configs.savemonData(mon_data)
    print(APPSRV + " of type " + SRVTYPE + " have been added")


if __name__ == "__main__":
    createMonJson()