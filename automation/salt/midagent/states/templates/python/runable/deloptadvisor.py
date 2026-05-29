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


def deleteOptAdvisorJson():
    srvtype = _arg(1, "SRVTYPE")
    appsrv = _arg(2, "APPSRV")
    opt_data = configs.getOptAdvisorData()

    if srvtype in opt_data and isinstance(opt_data.get(srvtype), dict):
        opt_data[srvtype].pop(appsrv, None)
        if len(opt_data[srvtype]) == 0:
            opt_data.pop(srvtype, None)

    configs.saveOptAdvisorData(opt_data)
    print(appsrv + " optadvisor configuration deleted")


if __name__ == "__main__":
    deleteOptAdvisorJson()
