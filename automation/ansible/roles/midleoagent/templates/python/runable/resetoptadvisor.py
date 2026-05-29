import importlib
import inspect
import os
import re
import sys

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import classes, configs
from modules.statistics import common

MODULE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


try:
    opt_data = configs.getOptAdvisorData()
    config_data = configs.getcfgData()
    website = config_data["MWADMIN"]
    webssl = config_data["SSLENABLED"]
    inttoken = config_data["INTTOKEN"]

    for srv_type, servers in opt_data.items():
        if not isinstance(servers, dict) or not MODULE_NAME_RE.fullmatch(str(srv_type)):
            continue
        try:
            stat_module = importlib.import_module(
                "modules.statistics." + srv_type + "." + srv_type
            )
        except Exception as err:
            classes.Err("OPTADVISOR unsupported statistics module:" + str(srv_type) + ":" + str(err))
            continue

        for appserver, value in servers.items():
            if not isinstance(value, dict):
                continue
            payload = dict(value)
            payload["optadvisor"] = True
            payload["optadvisor_enabled"] = True
            payload["optadvisor_only"] = True
            payload.setdefault("server_id", payload.get("appsrvid", appserver))
            payload.setdefault("optadvisor_technology", srv_type)
            if hasattr(stat_module, "flushOptAdvisorTelemetry"):
                stat_module.flushOptAdvisorTelemetry(appserver, website, webssl, inttoken, payload)
            else:
                common.flush_optadvisor_telemetry(srv_type, appserver, website, webssl, inttoken, payload)

except Exception as err:
    classes.Err("OPTADVISOR not configured err:" + str(err))
