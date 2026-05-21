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
    if len(sys.argv) != 4:
        raise ValueError("input: <type> <thisqm> <inpdata_json>")

    thistype = str(sys.argv[1]).strip()
    thisqm = str(sys.argv[2]).strip()
    if not thistype or not MODULE_NAME_RE.fullmatch(thistype):
        raise ValueError("invalid statistics type")
    if not thisqm:
        raise ValueError("empty queue manager/server name")

    inpdata_json = json.loads(sys.argv[3])
    if not isinstance(inpdata_json, dict):
        raise ValueError("inpdata_json must be a JSON object")

    stat_module = importlib.import_module(f"modules.statistics.{thistype}.{thistype}")

    config_data = configs.getcfgData()
    if not config_data.get("MWADMIN") or not config_data.get("SSLENABLED"):
        raise ValueError("backend configuration is missing")

    stat_module.getStat(thisqm, json.dumps(inpdata_json))

except Exception as err:
    classes.Err("getdockerstat error:" + str(err))
