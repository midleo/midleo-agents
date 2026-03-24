import sys
import os
import inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import configs

SRVTYPE = sys.argv[1]
APPSRV = sys.argv[2]


def deleteMonJson():
    mon_data = configs.getmonData()

    if SRVTYPE in mon_data and isinstance(mon_data.get(SRVTYPE), dict):
        mon_data[SRVTYPE].pop(APPSRV, None)
        if len(mon_data[SRVTYPE]) == 0:
            mon_data.pop(SRVTYPE, None)

    configs.savemonData(mon_data)
    print(APPSRV + " configuration deleted")


if __name__ == "__main__":
    deleteMonJson()