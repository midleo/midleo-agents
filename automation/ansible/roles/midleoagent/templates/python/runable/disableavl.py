import inspect
import os
import sys

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


def disableAvl():
    appsrv = _arg(1, "APPSRV")
    appsrvtype = _arg(2, "APPSRVTYPE")
    avl_data = configs.getAvlData()

    if appsrvtype in avl_data and isinstance(avl_data.get(appsrvtype), dict):
        avl_data[appsrvtype].pop(appsrv, None)
        if len(avl_data[appsrvtype]) == 0:
            avl_data.pop(appsrvtype, None)

    configs.saveAvlData(avl_data)
    print("Availability check for " + appsrv + " have been disabled")


if __name__ == "__main__":
    disableAvl()
