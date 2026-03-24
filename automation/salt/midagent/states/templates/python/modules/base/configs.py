import json
import os
import tempfile
import uuid

CONFIG_DIR = os.path.join(os.getcwd(), "config")
CRONJOBS_FILE = os.path.join(CONFIG_DIR, "cronjobs.json")

MON_FILE = os.path.join(CONFIG_DIR, "confapplstat.json")
CERT_FILE = os.path.join(CONFIG_DIR, "certs.json")
TRACK_FILE = os.path.join(CONFIG_DIR, "conftrack.json")
AVL_FILE = os.path.join(CONFIG_DIR, "confavl.json")

FILE_TO_CRONJOBS = {
    "conftrack.json": ["runmqtracker.py"],
    "confavl.json": ["runappavllin.py", "resetappavl.py", "runmqevents.py"],
    "confapplstat.json": ["getapplstat.py", "resetapplstat.py"],
}

SECTION_FILE_MAP = {
    "certs": CERT_FILE,
    "conftrack": TRACK_FILE,
    "confavl": AVL_FILE,
    "confapplstat": MON_FILE,
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
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


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
