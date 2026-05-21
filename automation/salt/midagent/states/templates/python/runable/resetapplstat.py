import importlib
import inspect
import os
import sys

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import classes, configs


def _load_statistics_modules():
    modules = {}
    stats_dir = os.path.join(parentdir, "modules", "statistics")
    for entry in os.scandir(stats_dir):
        if not entry.is_dir() or entry.name == "__pycache__":
            continue
        if not entry.name.replace("_", "").isalnum():
            continue
        module = importlib.import_module("modules.statistics." + entry.name + "." + entry.name)
        modules[entry.name] = module
    return modules


try:
    mon_data = configs.getmonData()
    config_data = configs.getcfgData()
    website = config_data["MWADMIN"]
    webssl = config_data["SSLENABLED"]
    inttoken = config_data["INTTOKEN"]
    stat_modules = _load_statistics_modules()

    for srvtype, servers in mon_data.items():
        module = stat_modules.get(srvtype)
        if module is None or not hasattr(module, "resetStat"):
            classes.Err("MQSTAT unsupported statistics module:" + str(srvtype))
            continue
        if not isinstance(servers, dict):
            continue
        for appserver, value in servers.items():
            module.resetStat(appserver, website, webssl, inttoken, value)

except Exception as err:
    classes.Err("MQSTAT not configured err:" + str(err))
