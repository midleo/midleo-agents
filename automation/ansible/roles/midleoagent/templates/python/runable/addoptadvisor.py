import json
import sys
import os
import inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import decrypt, configs, secrets

REMOVED_OPTADVISOR_AUTH_KEYS = secrets.REMOVED_AUTH_KEYS
IBMMQ_OPTADVISOR_DEFAULTS = {
    "collection_mode": "summary_plus_topn",
    "top_n_depth": 25,
    "top_n_age": 25,
    "max_queue_details_per_run": 100,
    "depth_percent_threshold": 70,
    "oldest_age_threshold_seconds": 1800,
    "include_patterns": [],
    "exclude_patterns": ["SYSTEM.*", "AMQ.*", "MQAI.*"],
    "deep_scan_interval_hours": 24,
    "collect_system_queues": False,
}


def _arg(index, name):
    try:
        value = sys.argv[index]
    except IndexError:
        raise ValueError("Missing required argument: " + name)
    value = str(value).strip()
    if not value:
        raise ValueError("Empty required argument: " + name)
    return value


def _store_value(key, value):
    if secrets.is_encrypted_secret_key(key) and value:
        return decrypt.encryptPWD(str(value))
    return value


def createOptAdvisorJson():
    srvtype = _arg(1, "SRVTYPE")
    appsrv = _arg(2, "APPSRV")
    raw_data = _arg(3, "OPTDATA")
    opt_data = configs.getOptAdvisorData()

    try:
        input_data = json.loads(raw_data) if raw_data else {}
    except Exception:
        raise ValueError("Invalid JSON for optadvisor configuration")

    if not isinstance(input_data, dict):
        raise ValueError("Optadvisor configuration must be a JSON object")

    if srvtype not in opt_data or not isinstance(opt_data.get(srvtype), dict):
        opt_data[srvtype] = {}

    if appsrv not in opt_data[srvtype] or not isinstance(opt_data[srvtype].get(appsrv), dict):
        opt_data[srvtype][appsrv] = {}

    opt_data[srvtype][appsrv]["optadvisor"] = True
    opt_data[srvtype][appsrv]["optadvisor_enabled"] = True
    opt_data[srvtype][appsrv]["optadvisor_only"] = True
    opt_data[srvtype][appsrv].setdefault("optadvisor_technology", srvtype)
    opt_data[srvtype][appsrv].setdefault("appserver", appsrv)
    opt_data[srvtype][appsrv].setdefault("monitoring_mode", "read_only")
    if srvtype == "ibmmq":
        for key, value in IBMMQ_OPTADVISOR_DEFAULTS.items():
            opt_data[srvtype][appsrv].setdefault(key, value)
    for removed_key in REMOVED_OPTADVISOR_AUTH_KEYS:
        opt_data[srvtype][appsrv].pop(removed_key, None)

    for key, value in input_data.items():
        if str(key).lower() in REMOVED_OPTADVISOR_AUTH_KEYS:
            continue
        if str(key).lower() == "pass" and "pwd" in input_data:
            continue
        store_key = "pwd" if str(key).lower() == "pass" else str(key)
        opt_data[srvtype][appsrv][store_key] = _store_value(store_key, value)

    appsrvid = str(opt_data[srvtype][appsrv].get("appsrvid", "")).strip()
    if appsrvid and appsrvid.lower() != "none" and not opt_data[srvtype][appsrv].get("server_id"):
        opt_data[srvtype][appsrv]["server_id"] = appsrvid

    configs.saveOptAdvisorData(opt_data)
    print(appsrv + " optadvisor configuration of type " + srvtype + " have been added")


if __name__ == "__main__":
    createOptAdvisorJson()
