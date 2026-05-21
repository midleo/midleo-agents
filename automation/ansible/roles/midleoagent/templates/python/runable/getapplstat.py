import json
import os
import sys
import inspect
import importlib
import re

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import classes, configs

MODULE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")

try:
    mon_data = configs.getmonData()
    config_data = configs.getcfgData()
    if not config_data.get("MWADMIN") or not config_data.get("SSLENABLED"):
        raise ValueError("backend configuration is missing")

    for srv_type, item in mon_data.items():
        if not item or not MODULE_NAME_RE.fullmatch(str(srv_type)):
            continue
        try:
            stat_module = importlib.import_module(
                f"modules.statistics.{srv_type}.{srv_type}"
            )
            for appsrv, val in item.items():
                if isinstance(val, dict):
                    stat_module.getStat(appsrv, json.dumps(val))
        except Exception as err:
            classes.Err("getapplstat module " + str(srv_type) + " error:" + str(err))

except Exception as err:
    classes.Err("getapplstat error:" + str(err))
