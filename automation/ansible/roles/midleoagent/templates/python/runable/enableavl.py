import json
import sys
import os
import inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import decrypt, configs


def _arg(index, name):
    try:
        value = sys.argv[index]
    except IndexError:
        raise ValueError("Missing required argument: " + name)
    value = str(value).strip()
    if not value:
        raise ValueError("Empty required argument: " + name)
    return value


def _json_arg(index):
    if len(sys.argv) <= index:
        return "{}"
    return " ".join(str(item) for item in sys.argv[index:])


def _strip_shell_wrapper(value):
    value = str(value).strip()

    for _ in range(2):
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1].strip()
            continue
        if value.startswith("'") and value[1:].lstrip().startswith("{"):
            value = value[1:].strip()
            continue
        if value.endswith("'") and value[:-1].rstrip().endswith("}"):
            value = value[:-1].strip()
            continue
        break

    return value


def _parse_json_arg(value):
    value = _strip_shell_wrapper(value)
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        pass

    start = value.find("{")
    if start < 0:
        raise ValueError("Invalid JSON for availability configuration")

    decoder = json.JSONDecoder()
    try:
        parsed, end = decoder.raw_decode(value[start:])
    except json.JSONDecodeError:
        raise ValueError(
            "Invalid JSON for availability configuration "
            + "(argv="
            + str(max(0, len(sys.argv) - 3))
            + ", length="
            + str(len(value))
            + ")"
        )

    return parsed


def createAvlJson():
    appsrv = _arg(1, "APPSRV")
    appsrvtype = _arg(2, "APPSRVTYPE")
    mondata = _json_arg(3)
    config_data = configs.getcfgData()
    uid = config_data.get("SRVUID", "")

    if not uid:
        raise RuntimeError("SRVUID is not set")

    avl_data = configs.getAvlData()

    monjsdata = _parse_json_arg(mondata)

    if not isinstance(monjsdata, dict):
        raise ValueError("Availability configuration must be a JSON object")

    if appsrvtype not in avl_data or not isinstance(avl_data.get(appsrvtype), dict):
        avl_data[appsrvtype] = {}

    avl_data[appsrvtype][appsrv] = {
        "enabled": "yes",
        "monid": "monapplavl",
        "dockercont": monjsdata["docker"] if "docker" in monjsdata else "",
        "usr": monjsdata["user"] if "user" in monjsdata else "",
        "ssl": monjsdata["ssl"] if "ssl" in monjsdata else "no",
        "appsrvid": monjsdata["appsrvid"] if "appsrvid" in monjsdata else "none",
        "mngmport": monjsdata["mngmport"] if "mngmport" in monjsdata else "",
        "pwd": decrypt.encryptPWD(monjsdata["pass"]) if "pass" in monjsdata else "",
    }

    configs.saveAvlData(avl_data)
    print("Availability check for " + appsrv + " have been enabled")


if __name__ == "__main__":
    createAvlJson()
