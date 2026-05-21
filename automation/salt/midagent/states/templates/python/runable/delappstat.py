import sys
import os
import inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import configs


def _arg(index, name):
    try:
        value = sys.argv[index]
    except IndexError:
        raise ValueError("Missing required argument: " + name)
    value = str(value).strip()
    if not value:
        raise ValueError("Empty required argument: " + name)
    return value


def deleteMonJson():
    srvtype = _arg(1, "SRVTYPE")
    appsrv = _arg(2, "APPSRV")
    mon_data = configs.getmonData()

    if srvtype in mon_data and isinstance(mon_data.get(srvtype), dict):
        mon_data[srvtype].pop(appsrv, None)
        if len(mon_data[srvtype]) == 0:
            mon_data.pop(srvtype, None)

    configs.savemonData(mon_data)
    print(appsrv + " configuration deleted")


if __name__ == "__main__":
    deleteMonJson()
