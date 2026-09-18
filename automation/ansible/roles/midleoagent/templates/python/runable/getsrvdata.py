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

from modules.base import makerequest, classes, certcheck, configs, appsrv_discover, vulnerability_inventory
from midleo_client import AGENT_VER
from getlocaljobs import getLocalJobsBody

OS_TYPE = platform.system()
OS_RELEASE = platform.release()
ZOS_OS_TYPES = {"OS/390", "z/OS"}
BASE_DIR = os.getcwd()
CONFIG_DIR = os.path.join(BASE_DIR, "config")
CERTS_FILE = os.path.join(CONFIG_DIR, "certs.json")
NEXTRUN_FILE = os.path.join(CONFIG_DIR, "nextrun.txt")

if OS_TYPE == "Linux" or OS_TYPE in ZOS_OS_TYPES:
    from modules.base import lin_utils, lin_packages
elif OS_TYPE == "Windows":
    from modules.base import win_utils
else:
    raise RuntimeError("Unsupported operating system: " + OS_TYPE)

def _safe_get_config():
    config_data = configs.getcfgData()
    if not config_data:
        raise RuntimeError("configs.getcfgData() returned empty data")

    required_keys = ("SRVUID", "GROUPID", "UPDINT", "MWADMIN", "SSLENABLED")
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

def _safe_application_evidence_windows():
    try:
        data = win_utils.getApplicationServerEvidence()
        return data if isinstance(data, list) else None
    except Exception as ex:
        classes.Err("Exception in win_utils.getApplicationServerEvidence(): " + str(ex))
        return None

def _safe_application_evidence_linux():
    try:
        data = lin_packages.getApplicationServerEvidence()
        return data if isinstance(data, list) else None
    except Exception as ex:
        classes.Err("Exception in lin_packages.getApplicationServerEvidence(): " + str(ex))
        return None

def _safe_jobsdata():
    try:
        data = getLocalJobsBody()
        if isinstance(data, dict):
            return data
    except Exception as ex:
        classes.Err("Exception in getLocalJobsBody(): " + str(ex))
    return {"jobs": []}

def _attach_application_servers(config, evidence, settings=None):
    if evidence is None:
        return
    try:
        observations = appsrv_discover.discover_application_servers(
            evidence,
            os_type=OS_TYPE,
            os_release=OS_RELEASE,
        )
        observations = vulnerability_inventory.identify_variants(observations, evidence)
        observations = vulnerability_inventory.enrich(
            observations, evidence, settings if settings is not None else configs.getcfgData(), os_type=OS_TYPE,
        )
        config.application_servers = observations
    except Exception as ex:
        classes.Err("Exception in application server discovery: " + str(ex))

def _build_windows_config(uid, groupid, updint, certs):
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
    evidence = _safe_application_evidence_windows()

    config = classes.Config(
        uid,
        groupid,
        AGENT_VER,
        updint,
        hw_config.__dict__,
        net_config.__dict__,
        certs
    )
    _attach_application_servers(config, evidence)
    return config

def _build_linux_config(uid, groupid, updint, certs):
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
    evidence = _safe_application_evidence_linux()

    config = classes.Config(
        uid,
        groupid,
        AGENT_VER,
        updint,
        hw_config.__dict__,
        net_config.__dict__,
        certs
    )
    _attach_application_servers(config, evidence)
    return config

def _sanitize_output(output):
    output = re.sub(r"<([a-zA-Z\-_]+)?\.([a-zA-Z\-_]+)(\d?):(\s?)", "", output)
    output = re.sub(r">", "", output)
    return output

def _write_next_run(updint):
    timenow = datetime.now() + timedelta(minutes=updint)
    tmp_file = NEXTRUN_FILE + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as log_file:
        log_file.write(str(int(timenow.timestamp())))
    os.replace(tmp_file, NEXTRUN_FILE)
    try:
        os.chmod(NEXTRUN_FILE, 0o600)
    except Exception:
        pass

def create():
    try:
        config_data = _safe_get_config()
        uid = config_data["SRVUID"]
        groupid = config_data["GROUPID"]
        updint = int(config_data["UPDINT"])
    
        certs = _safe_cert_check(uid)
        jobsdata = _safe_jobsdata()

        if OS_TYPE == "Windows":
            config = _build_windows_config(uid, groupid, updint, certs)
        elif OS_TYPE == "Linux" or OS_TYPE in ZOS_OS_TYPES:
            config = _build_linux_config(uid, groupid, updint, certs)
        else:
            raise RuntimeError("Unsupported operating system: " + OS_TYPE)

        if config is None:
            raise RuntimeError("classes.Config() returned None")

        config.jobsdata = jobsdata
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
