import json
import os
import platform
import re
import inspect
import sys
from datetime import datetime, timedelta

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import makerequest, classes, certcheck, configs
from midleo_client import AGENT_VER

OS_TYPE = platform.system()
BASE_DIR = os.getcwd()
CONFIG_DIR = os.path.join(BASE_DIR, "config")
CERTS_FILE = os.path.join(CONFIG_DIR, "certs.json")
NEXTRUN_FILE = os.path.join(CONFIG_DIR, "nextrun.txt")

if OS_TYPE == "Linux":
    from modules.base import lin_utils, lin_packages
elif OS_TYPE == "Windows":
    from modules.base import win_utils
else:
    raise RuntimeError("Unsupported operating system: " + OS_TYPE)


def _safe_get_config():
    config_data = configs.getcfgData()
    if not config_data:
        raise RuntimeError("configs.getcfgData() returned empty data")

    required_keys = ("SRVUID", "GROUPID", "UPDINT", "INTTOKEN", "MWADMIN", "SSLENABLED")
    missing = [key for key in required_keys if key not in config_data or config_data[key] in (None, "")]
    if missing:
        raise RuntimeError("Missing required configuration keys: " + ",".join(missing))

    return config_data


def _safe_cert_check(uid):
    if not os.path.isfile(CERTS_FILE):
        return []

    try:
        return certcheck.Run(uid * 4) or []
    except Exception as ex:
        classes.Err("Exception in certificate check: " + str(ex))
        return []


def _safe_software_windows():
    try:
        data = win_utils.getSoftware()
        return data if data is not None else []
    except Exception as ex:
        classes.Err("Exception in win_utils.getSoftware(): " + str(ex))
        return []


def _safe_software_linux():
    try:
        data = lin_packages.getSoftware()
        return data if data is not None else []
    except Exception as ex:
        classes.Err("Exception in lin_packages.getSoftware(): " + str(ex))
        return []


def _build_windows_config(uid, inttoken, groupid, updint, certs):
    cpu = classes.CPU(win_utils.getCPUName(), win_utils.getCPUCoreCount())
    hw_config = classes.HWConfig(
        win_utils.getName(),
        win_utils.getOS(),
        win_utils.getArchitecture(),
        win_utils.getMachineType(),
        cpu.__dict__,
        win_utils.getMemory(),
        win_utils.getDiskPartitions(),
        win_utils.getLBTS()
    )
    net_config = classes.NetConfig(win_utils.getIP())
    software = _safe_software_windows()

    return classes.Config(
        uid,
        inttoken,
        groupid,
        AGENT_VER,
        updint,
        hw_config.__dict__,
        net_config.__dict__,
        software,
        certs
    )


def _build_linux_config(uid, inttoken, groupid, updint, certs):
    cpu = classes.CPU(lin_utils.getCPUName(), lin_utils.getCPUCoreCount())
    hw_config = classes.HWConfig(
        lin_utils.getName(),
        lin_utils.getOS(),
        lin_utils.getArchitecture(),
        lin_utils.getMachineType(),
        cpu.__dict__,
        lin_utils.getMemory(),
        lin_utils.getDiskPartitions(),
        lin_utils.getLBTS()
    )
    net_config = classes.NetConfig(lin_utils.getIP())
    software = _safe_software_linux()

    return classes.Config(
        uid,
        inttoken,
        groupid,
        AGENT_VER,
        updint,
        hw_config.__dict__,
        net_config.__dict__,
        software,
        certs
    )


def _sanitize_output(output):
    output = re.sub(r"<([a-zA-Z\-_]+)?\.([a-zA-Z\-_]+)(\d?):(\s?)", "", output)
    output = re.sub(r">", "", output)
    return output


def _write_next_run(updint):
    timenow = datetime.now() + timedelta(minutes=updint)
    with open(NEXTRUN_FILE, "w", encoding="utf-8") as log_file:
        log_file.write(str(int(timenow.timestamp())))


def create():
    try:
        config_data = _safe_get_config()
        uid = config_data["SRVUID"]
        groupid = config_data["GROUPID"]
        updint = int(config_data["UPDINT"])
        inttoken = config_data["INTTOKEN"]

        certs = _safe_cert_check(uid)

        if OS_TYPE == "Windows":
            config = _build_windows_config(uid, inttoken, groupid, updint, certs)
        elif OS_TYPE == "Linux":
            config = _build_linux_config(uid, inttoken, groupid, updint, certs)
        else:
            raise RuntimeError("Unsupported operating system: " + OS_TYPE)

        if config is None:
            raise RuntimeError("classes.Config() returned None")

        return config

    except OSError as err:
        classes.Err("Error in create: " + str(err))
    except Exception as ex:
        classes.Err("Exception in create: " + str(ex))

    return None


def main():
    try:
        config = create()
        if config is None:
            return

        if getattr(config, "error", None):
            return

        config_data = _safe_get_config()
        website = config_data["MWADMIN"]
        webssl = config_data["SSLENABLED"]
        updint = int(config_data["UPDINT"])

        output = json.dumps(config.__dict__, default=str)
        output = _sanitize_output(output)

        makerequest.postData(webssl, website, json.loads(output))
        _write_next_run(updint)

    except OSError as err:
        classes.Err("Error in main: " + str(err))
    except Exception as ex:
        classes.Err("Exception in main: " + str(ex))


if __name__ == "__main__":
    main()