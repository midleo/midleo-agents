import glob
import json
import os
import subprocess

from modules.base import classes, file_utils, makerequest, statarr

DEFAULT_TIMEOUT_SECONDS = int(os.environ.get("MIDLEO_STAT_TIMEOUT_SECONDS", "45"))
MAX_LOG_BYTES = 4000


def parse_json_object(payload):
    data = json.loads(payload) if isinstance(payload, str) else payload
    if not isinstance(data, dict):
        raise ValueError("statistics input must be a JSON object")
    return data


def pop_fields(data, field_defaults):
    source = dict(data)
    values = {}
    for key, default in field_defaults.items():
        values[key] = source.pop(key, default)
    return values, source


def first_value(data):
    if not data:
        raise ValueError("statistics input has no metrics")
    return next(iter(data.values()))


def run_command(command, label, timeout=DEFAULT_TIMEOUT_SECONDS):
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        classes.Err(label + " timed out after " + str(timeout) + " seconds")
        return False
    except OSError as err:
        classes.Err(label + " failed to start:" + str(err))
        return False

    if result.stdout:
        classes.Err(label + " Output:" + result.stdout[-MAX_LOG_BYTES:])
    if result.stderr:
        classes.Err(label + " Error:" + result.stderr[-MAX_LOG_BYTES:])
    if result.returncode != 0:
        classes.Err(label + " failed with exit code " + str(result.returncode))
        return False
    return True


def post_csv_stats(stat_type, func_name, website, webssl, inttoken, stat_data, pattern_fn):
    try:
        if not isinstance(stat_data, dict) or len(stat_data) == 0:
            return

        for subtype, logdir in stat_data.items():
            resolved_func_name = func_name(subtype) if callable(func_name) else func_name
            func = getattr(statarr, resolved_func_name, None)
            if func is None:
                classes.Err("Missing stat array for " + stat_type + ":" + resolved_func_name)
                continue

            for file_path in glob.glob(pattern_fn(str(logdir), str(subtype))):
                ret = file_utils.csv_json(file_path, func(), "", True)
                retarr = json.loads(ret)
                if len(retarr) == 0:
                    continue

                payload = {
                    "type": stat_type,
                    "inttoken": inttoken,
                    "subtype": subtype,
                    "data": retarr,
                }
                makerequest.postStatData(webssl, website, json.dumps(payload))

    except OSError as err:
        classes.Err("Error opening the file statlist:" + str(err))
    except (json.JSONDecodeError, TypeError, ValueError) as err:
        classes.Err("Error parsing statlist:" + str(err))
