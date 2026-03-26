import json
import os
import sys
import inspect
import importlib

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import classes, configs

try:
    mon_data = configs.getmonData()
    config_data = configs.getcfgData()
    website = config_data["MWADMIN"]
    webssl = config_data["SSLENABLED"]

    for srv_type, item in mon_data.items():
        if not item:
            continue
        stat_module = importlib.import_module(
            f"modules.statistics.{srv_type}.{srv_type}"
        )
        for appsrv, val in item.items():
            stat_module.getStat(appsrv, json.dumps(val))

except Exception as err:
    classes.Err("getapplstat error:" + str(err))
