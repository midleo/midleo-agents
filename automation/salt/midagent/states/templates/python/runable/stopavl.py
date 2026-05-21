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


def stopAvl():
    usr = _arg(1, "USR")
    appsrv = _arg(2, "APPSRV")
    appsrvtype = _arg(3, "APPSRVTYPE")
    comment = _arg(4, "COMMENT")

    avl_data = configs.getAvlData()
    if appsrvtype not in avl_data or appsrv not in avl_data.get(appsrvtype, {}):
        raise ValueError("No such availability for:" + appsrv)

    avl_data[appsrvtype][appsrv]["enabled"] = "no"
    configs.saveAvlData(avl_data)
    classes.WriteData(
        "stopped," + usr + "," + comment,
        "avl_" + appsrvtype + "_" + appsrv + ".csv",
    )
    print("Availability check for " + appsrv + " have been stopped")


if __name__ == "__main__":
    stopAvl()
