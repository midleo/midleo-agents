import sys
import os
import inspect
import re

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import configs

JOB_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _arg(index, name):
    try:
        value = sys.argv[index]
    except IndexError:
        raise ValueError("Missing required argument: " + name)
    value = str(value).strip()
    if not value:
        raise ValueError("Empty required argument: " + name)
    return value


def _root_config(config_data):
    config_data = config_data if isinstance(config_data, dict) else {}
    root = config_data.get("message_backup")
    return root if isinstance(root, dict) else config_data


def _as_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on")


def remove_message_backup():
    job_name = _arg(1, "JOB_NAME")
    if not JOB_NAME_RE.fullmatch(job_name):
        raise ValueError("JOB_NAME may contain only letters, numbers, dot, underscore and dash")
    config_data = configs.getMessageBackupData()
    root = _root_config(config_data)
    if not isinstance(root, dict):
        print("Message backup job " + job_name + " removed")
        return

    jobs = root.get("jobs") if isinstance(root.get("jobs"), list) else []
    root["jobs"] = [
        job
        for job in jobs
        if not (isinstance(job, dict) and str(job.get("name", "")).strip() == job_name)
    ]
    root["enabled"] = any(
        isinstance(job, dict) and _as_bool(job.get("enabled"), True) for job in root["jobs"]
    )
    configs.saveMessageBackupData(config_data)
    print("Message backup job " + job_name + " removed")


if __name__ == "__main__":
    remove_message_backup()
