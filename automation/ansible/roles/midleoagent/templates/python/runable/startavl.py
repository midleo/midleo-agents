import inspect
import os
import sys

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import classes, configs


def _arg(index, name):
    try:
        value = sys.argv[index]
    except IndexError:
        raise ValueError("Missing required argument: " + name)
    value = str(value).strip()
    if not value:
        raise ValueError("Empty required argument: " + name)
    return value


def startAvl():
    usr = _arg(1, "USR")
    appsrv = _arg(2, "APPSRV")
    appsrvtype = _arg(3, "APPSRVTYPE")

    avl_data = configs.getAvlData()
    if appsrvtype not in avl_data or appsrv not in avl_data.get(appsrvtype, {}):
        raise ValueError("No such availability for:" + appsrv)

    avl_data[appsrvtype][appsrv]["enabled"] = "yes"
    configs.saveAvlData(avl_data)
    classes.WriteData("started," + usr, "avl_" + appsrvtype + "_" + appsrv + ".csv")
    print("Availability check for " + appsrv + " have been started")


if __name__ == "__main__":
    startAvl()
