import os
import platform
import re
import threading
from datetime import datetime

LOG_DIR = os.path.join(os.getcwd(), "logs")
AGENT_LOG = os.path.join(LOG_DIR, "midleoagent.log")
MAX_LOG_BYTES = int(os.environ.get("MIDLEO_MAX_LOG_BYTES", str(5 * 1024 * 1024)))
_LOG_LOCK = threading.Lock()
_SECRET_RE = re.compile(
    r'("?(?:pwd|pass|password|srvpass|cpass|chlpass|inttoken|token)"?\s*[:=]\s*)'
    r'(".*?"|\'.*?\'|[^,\}\s]+)',
    re.IGNORECASE,
)


def _safe_text(value):
    text = str(value)
    return _SECRET_RE.sub(r'\1"..."', text)


def _ensure_log_dir():
    os.makedirs(LOG_DIR, exist_ok=True)


def _rotate_log(path):
    try:
        if os.path.exists(path) and os.path.getsize(path) > MAX_LOG_BYTES:
            rotated = path + ".1"
            if os.path.exists(rotated):
                os.remove(rotated)
            os.replace(path, rotated)
    except Exception:
        pass


def _write_log(path, line):
    with _LOG_LOCK:
        _ensure_log_dir()
        _rotate_log(path)
        with open(path, "a", encoding="utf-8") as logfile:
            logfile.write(line + "\n")


def ClearLog():
    current_time = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    _write_log(AGENT_LOG, current_time + ":Info:Service started")
    
def Err(logdata):
    current_time = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    _write_log(AGENT_LOG, current_time + ":" + _safe_text(logdata))

class CPU:
    def __init__(self, name, num_cores):
        self.name = name
        self.num_cores = num_cores

class HWConfig:
    def __init__(self, name, os, architecture, machine_type, cpu, memory, disk_partitions, last_boot_time):
        self.name = name
        self.servtype = os
        self.servos = str(platform.system()).lower()
        self.architecture = architecture
        self.machineType = machine_type
        self.cpu = cpu
        self.memory = memory
        self.disk_partitions = disk_partitions
        self.last_boot_time = last_boot_time

class NetConfig:
    def __init__(self, dns):
        self.dns = dns
        
class Config:
    def __init__(self, uid, inttoken, groupid, agtver, updint, hw, net, geo, certs):
        self.uid = uid
        self.inttoken = inttoken
        self.groupid = groupid
        self.agtver = agtver
        self.updint = updint
        self.hw_info = hw
        self.net_info = net
        self.installed_software = geo
        self.certs = certs

def WriteData(logdata,logfile):
    now = datetime.now()
    current_time = now.strftime("%Y-%m-%d %H:%M:%S")
    safe_name = os.path.basename(logfile)
    path = os.path.join(LOG_DIR, safe_name)
    _write_log(path, current_time + "," + str(logdata))
