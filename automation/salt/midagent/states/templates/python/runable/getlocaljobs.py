import json
import os
import inspect
from datetime import datetime

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
import sys

sys.path.insert(0, parentdir)

from modules.base import configs

CRON_STATE_FILE = os.path.join(os.getcwd(), "config", "cron_state.json")


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _sanitize_dict(data):
    if not isinstance(data, dict):
        return {}

    hidden_keys = {"pwd", "pass", "usr", "user", "cpass", "ssl", "mngmport"}
    result = {}

    for key, value in data.items():
        if key in hidden_keys:
            continue
        result[key] = value

    return result


def _append_job(jobs_map, job_name, item):
    if job_name not in jobs_map:
        jobs_map[job_name] = {
            "name": job_name,
            "type": "cronjob",
            "value": {
                "last_run": None,
                "finished_at": None,
                "exit_code": None,
                "args": [],
            },
        }

    jobs_map[job_name].setdefault("data", [])
    jobs_map[job_name]["data"].append(item)


def getLocalJobsBody():
    jobs_map = {}

    cron_state = _read_json(CRON_STATE_FILE)
    for script_name, item in cron_state.items():
        if not isinstance(item, dict):
            continue

        jobs_map[script_name] = {
            "name": script_name,
            "type": "cronjob",
            "value": {
                "last_run": item.get("last_run", ""),
                "finished_at": item.get("finished_at", ""),
                "exit_code": item.get("exit_code", ""),
                "args": item.get("args", []),
            },
            "data": [],
        }

    avl_data = configs.getAvlData()
    for srvtype, servers in avl_data.items():
        if not isinstance(servers, dict):
            continue

        for appserver, item in servers.items():
            if not isinstance(item, dict):
                continue

            clean_item = _sanitize_dict(item)

            entry = {
                "name": appserver,
                "type": "appserver",
                "value": {"srvtype": srvtype, **clean_item},
            }

            _append_job(jobs_map, "runappavllin.py", entry)
            _append_job(jobs_map, "resetappavl.py", entry)

    mon_data = configs.getmonData()
    for srvtype, servers in mon_data.items():
        if not isinstance(servers, dict):
            continue

        for appserver, item in servers.items():
            if not isinstance(item, dict):
                continue

            entry = {
                "name": appserver,
                "type": "appstat",
                "value": {"srvtype": srvtype, "config": _sanitize_dict(item)},
            }

            _append_job(jobs_map, "getapplstat.py", entry)
            _append_job(jobs_map, "resetapplstat.py", entry)

    track_data = configs.gettrackData()
    for qmgr, item in track_data.items():
        entry = {
            "name": qmgr,
            "type": "trackqm",
            "value": _sanitize_dict(item) if isinstance(item, dict) else {},
        }

        _append_job(jobs_map, "runmqtracker.py", entry)

    cert_data = configs.getcertData()
    for cert_key, item in cert_data.items():
        if not isinstance(item, dict):
            continue

        entry = {
            "name": cert_key,
            "type": "keystore",
            "value": {
                "command": item.get("command", ""),
                "cfile": item.get("cfile", ""),
                "clabel": item.get("clabel", ""),
                "exclude_aliases": item.get("exclude_aliases", ""),
            },
        }

        _append_job(jobs_map, "getsrvdata.py", entry)

    jobs = list(jobs_map.values())

    return {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "jobs": jobs}


if __name__ == "__main__":
    print(json.dumps(getLocalJobsBody(), ensure_ascii=False))
