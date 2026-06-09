import json
import os
import tempfile
import uuid
from datetime import datetime, timezone

CONFIG_DIR = os.path.join(os.getcwd(), "config")
CRONJOBS_FILE = os.path.join(CONFIG_DIR, "cronjobs.json")
AGENT_IDENTITY_FILE = os.path.join(CONFIG_DIR, "agent.identity")
UPLOAD_STATE_FILE = os.path.join(CONFIG_DIR, "upload_state.json")

MON_FILE = os.path.join(CONFIG_DIR, "confapplstat.json")
OPTADVISOR_FILE = os.path.join(CONFIG_DIR, "confoptadvisor.json")
CERT_FILE = os.path.join(CONFIG_DIR, "certs.json")
TRACK_FILE = os.path.join(CONFIG_DIR, "conftrack.json")
AVL_FILE = os.path.join(CONFIG_DIR, "confavl.json")
ACTIONS_FILE = os.path.join(CONFIG_DIR, "confactions.json")

FILE_TO_CRONJOBS = {
    "conftrack.json": ["runmqtracker.py"],
    "confavl.json": ["runappavllin.py", "resetappavl.py", "runmqevents.py"],
    "confapplstat.json": ["getapplstat.py", "resetapplstat.py"],
    "confoptadvisor.json": ["getoptadvisor.py", "resetoptadvisor.py"],
}

DEFAULT_CRONJOB_DEFS = {
    "getoptadvisor.py": {
        "config_file": "confoptadvisor.json",
        "timeout_seconds": 300,
        "run": {
            "minute_in": ["00", "10", "20", "30", "40", "50"],
        },
    },
    "resetoptadvisor.py": {
        "config_file": "confoptadvisor.json",
        "timeout_seconds": 300,
        "run": {
            "minute_in": ["05", "15", "25", "35", "45", "55"],
        },
    },
}

SECTION_FILE_MAP = {
    "certs": CERT_FILE,
    "conftrack": TRACK_FILE,
    "confavl": AVL_FILE,
    "confapplstat": MON_FILE,
    "confoptadvisor": OPTADVISOR_FILE,
    "confactions": ACTIONS_FILE,
}


def _ensure_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def _read_json_file(path, default=None):
    if default is None:
        default = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else default
    except Exception:
        return default


def _write_json_atomic(path, data):
    _ensure_dir()
    fd, tmp_path = tempfile.mkstemp(
        prefix=".tmp_" + str(uuid.uuid4()) + "_", dir=os.path.dirname(path)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            json.dump(data, tmp_file, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp_path, path)
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _write_identity_atomic(data):
    _ensure_dir()
    fd, tmp_path = tempfile.mkstemp(
        prefix=".tmp_identity_" + str(uuid.uuid4()) + "_", dir=os.path.dirname(AGENT_IDENTITY_FILE)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            json.dump(data, tmp_file, ensure_ascii=False, indent=2, sort_keys=True)
            tmp_file.write("\n")
        os.replace(tmp_path, AGENT_IDENTITY_FILE)
        try:
            os.chmod(AGENT_IDENTITY_FILE, 0o600)
        except Exception:
            pass
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def getAgentIdentity():
    env_agent_id = os.environ.get("MIDLEO_AGENT_ID", "").strip()
    env_agent_token = os.environ.get("MIDLEO_AGENT_TOKEN", "").strip()
    if env_agent_id and env_agent_token:
        return {"agent_id": env_agent_id, "agent_token": env_agent_token, "source": "env"}
    data = _read_json_file(AGENT_IDENTITY_FILE, {})
    if data.get("agent_id") and data.get("agent_token"):
        data["source"] = "file"
        return data
    return {}


def getInstallationId():
    env_installation_id = (
        os.environ.get("MIDLEO_AGENT_INSTALLATION_ID", "")
        or os.environ.get("MIDLEO_INSTALLATION_ID", "")
    ).strip()
    if env_installation_id:
        return env_installation_id
    data = _read_json_file(AGENT_IDENTITY_FILE, {})
    if data.get("installation_id"):
        return str(data["installation_id"])
    data["installation_id"] = str(uuid.uuid4())
    data["created_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    _write_identity_atomic(data)
    return data["installation_id"]


def saveAgentIdentity(agent_id, agent_token, extra=None):
    if not agent_id or not agent_token:
        return
    data = _read_json_file(AGENT_IDENTITY_FILE, {})
    data.update(extra or {})
    data["agent_id"] = str(agent_id)
    data["agent_token"] = str(agent_token)
    data["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    _write_identity_atomic(data)


def _has_items(data):
    return isinstance(data, dict) and len(data) > 0


def _section_to_file(section_name):
    return SECTION_FILE_MAP.get(section_name)


def getcfgData():
    parser = {}
    try:
        with open(
            os.path.join(CONFIG_DIR, "mwagent.config"), "r", encoding="utf-8"
        ) as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                parser[key.strip()] = value.strip()
    except Exception:
        parser = {}
    return parser


def getCronjobs():
    return _read_json_file(CRONJOBS_FILE, {})


def saveCronjobs(data):
    if not isinstance(data, dict):
        data = {}
    _write_json_atomic(CRONJOBS_FILE, data)


def getUploadState():
    return _read_json_file(UPLOAD_STATE_FILE, {})


def saveUploadState(data):
    if not isinstance(data, dict):
        data = {}
    _write_json_atomic(UPLOAD_STATE_FILE, data)


def syncCronjobsForConfig(config_filename, config_data):
    jobs = FILE_TO_CRONJOBS.get(config_filename, [])
    if not jobs:
        return

    cronjobs = getCronjobs()
    enabled = _has_items(config_data)

    for job_name in jobs:
        job_def = cronjobs.get(job_name, {})
        if not isinstance(job_def, dict):
            job_def = {}
        for key, value in DEFAULT_CRONJOB_DEFS.get(job_name, {}).items():
            if key not in job_def or job_def[key] in (None, {}, []):
                job_def[key] = value
        job_def["enabled"] = enabled
        cronjobs[job_name] = job_def

    saveCronjobs(cronjobs)


def _get_config(path):
    return _read_json_file(path, {})


def _save_config(path, data, config_filename=None):
    if not isinstance(data, dict):
        data = {}
    _write_json_atomic(path, data)
    if config_filename:
        syncCronjobsForConfig(config_filename, data)


def getSection(section_name):
    path = _section_to_file(section_name)
    if not path:
        return {}
    return _get_config(path)


def setSection(section_name, section_data):
    path = _section_to_file(section_name)
    if not path:
        return
    _save_config(path, section_data, os.path.basename(path))


def upsertSectionItem(section_name, item_key, item_value):
    path = _section_to_file(section_name)
    if not path:
        return
    data = _get_config(path)
    data[item_key] = item_value
    _save_config(path, data, os.path.basename(path))


def deleteSectionItem(section_name, item_key):
    path = _section_to_file(section_name)
    if not path:
        return
    data = _get_config(path)
    if item_key in data:
        del data[item_key]
    _save_config(path, data, os.path.basename(path))


def getmonData():
    return _get_config(MON_FILE)


def savemonData(data):
    _save_config(MON_FILE, data, "confapplstat.json")


def getOptAdvisorData():
    return _get_config(OPTADVISOR_FILE)


def saveOptAdvisorData(data):
    _save_config(OPTADVISOR_FILE, data, "confoptadvisor.json")


def getcertData():
    return _get_config(CERT_FILE)


def savecertData(data):
    _save_config(CERT_FILE, data)


def gettrackData():
    return _get_config(TRACK_FILE)


def savetrackData(data):
    _save_config(TRACK_FILE, data, "conftrack.json")


def getAvlData():
    return _get_config(AVL_FILE)


def saveAvlData(data):
    _save_config(AVL_FILE, data, "confavl.json")


def getActionData():
    return _get_config(ACTIONS_FILE)


def saveActionData(data):
    _save_config(ACTIONS_FILE, data, "confactions.json")
