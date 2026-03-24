import json
import sys
import os
import inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import decrypt, configs

APPSRV = sys.argv[1]
APPSRVTYPE = sys.argv[2]
MONDATA = sys.argv[3] if len(sys.argv) >= 4 else "{}"

def createAvlJson():
    config_data = configs.getcfgData()
    uid = config_data.get("SRVUID", "")

    if not uid:
        pass

    avl_data = configs.getAvlData()

    try:
        monjsdata = json.loads(MONDATA)
    except Exception:
        monjsdata = {}

    if APPSRVTYPE not in avl_data or not isinstance(avl_data.get(APPSRVTYPE), dict):
        avl_data[APPSRVTYPE] = {}

    avl_data[APPSRVTYPE][APPSRV] = {
        "enabled": "yes",
        "monid": "monapplavl",
        "dockercont": monjsdata["docker"] if "docker" in monjsdata else "",
        "usr": monjsdata["user"] if "user" in monjsdata else "",
        "ssl": monjsdata["ssl"] if "ssl" in monjsdata else "no",
        "appsrvid": monjsdata["appsrvid"] if "appsrvid" in monjsdata else "none",
        "mngmport": monjsdata["mngmport"] if "mngmport" in monjsdata else "",
        "pwd": decrypt.encryptPWD(monjsdata["pass"]) if "pass" in monjsdata else "",
    }

    configs.saveAvlData(avl_data)
    print("Availability check for " + APPSRV + " have been enabled")


if __name__ == "__main__":
    createAvlJson()
