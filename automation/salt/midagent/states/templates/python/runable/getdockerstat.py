import json
import os
import sys
import inspect
import importlib

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import classes, configs

if len(sys.argv) != 4:
    print("input: <type> <thisqm> <inpdata_json>")
    sys.exit(1)

thistype = sys.argv[1]
thisqm = sys.argv[2]
inpdata_json = json.loads(sys.argv[3])

try:
    stat_module = importlib.import_module(f"modules.statistics.{thistype}.{thistype}")

    mon_data = configs.getmonData()
    config_data = configs.getcfgData()
    website = config_data["MWADMIN"]
    webssl = config_data["SSLENABLED"]

    runstat = stat_module.getStat(thisqm, json.dumps(inpdata_json))

except Exception as err:
    classes.Err(thistype + " error:" + str(err))