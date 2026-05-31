import importlib
import inspect
import json
import os
import re
import sys
import time

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import classes, configs
from modules.statistics import common

MODULE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


try:
    lock = None
    runtime_status = common.optadvisor_runtime_status()
    if not runtime_status.get("active"):
        classes.Err("getoptadvisor skipped runtime status:" + str(runtime_status.get("status", "unknown")))
        raise SystemExit(0)

    opt_data = configs.getOptAdvisorData()
    if not opt_data:
        classes.Err("getoptadvisor skipped no confoptadvisor entries")
        raise SystemExit(0)

    lock = common.acquire_optadvisor_lock("runtime")
    if not lock:
        classes.Err("getoptadvisor skipped optadvisor runtime lock active")
        raise SystemExit(0)

    config_data = configs.getcfgData()
    if not config_data.get("MWADMIN") or not config_data.get("SSLENABLED"):
        raise ValueError("backend configuration is missing")

    processed = 0
    started = time.time()
    max_seconds = common.optadvisor_run_seconds_limit()
    for srv_type, servers in opt_data.items():
        if time.time() - started > max_seconds:
            classes.Err("getoptadvisor stopped after bounded runtime seconds:" + str(max_seconds))
            break
        if not servers or not MODULE_NAME_RE.fullmatch(str(srv_type)):
            continue
        try:
            stat_module = importlib.import_module(
                f"modules.statistics.{srv_type}.{srv_type}"
            )
            for appsrv, value in servers.items():
                if time.time() - started > max_seconds:
                    classes.Err("getoptadvisor stopped after bounded runtime seconds:" + str(max_seconds))
                    break
                if not isinstance(value, dict):
                    continue
                if not common.optadvisor_enabled(value):
                    continue
                payload = dict(value)
                payload["optadvisor"] = True
                payload["optadvisor_enabled"] = True
                payload["optadvisor_only"] = True
                payload.setdefault("server_id", payload.get("appsrvid", appsrv))
                payload.setdefault("optadvisor_technology", srv_type)
                processed += 1
                classes.Err("getoptadvisor running " + str(srv_type) + " " + str(appsrv))
                stat_module.getStat(appsrv, json.dumps(payload))
        except Exception as err:
            classes.Err("getoptadvisor module " + str(srv_type) + " error:" + str(err))

    if processed == 0:
        classes.Err("getoptadvisor skipped no enabled server entries")

except Exception as err:
    classes.Err("getoptadvisor error:" + str(err))
finally:
    try:
        common.release_optadvisor_lock(lock)
    except NameError:
        pass
