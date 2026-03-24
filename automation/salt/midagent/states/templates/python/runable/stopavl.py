import sys
import os
import inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import classes, configs

USR = sys.argv[1]
APPSRV = sys.argv[2]
APPSRVTYPE = sys.argv[3]
COMMENT = sys.argv[4]

try:
    avl_data = configs.getAvlData()
    avl_data[APPSRVTYPE][APPSRV]["enabled"] = "no"
    configs.saveAvlData(avl_data)
    classes.WriteData("stopped," + USR + "," + COMMENT, "avl_" + APPSRVTYPE + "_" + APPSRV + ".csv")
    print("Availability check for " + APPSRV + " have been stopped")
except Exception:
    print("No such availability for:" + APPSRV)