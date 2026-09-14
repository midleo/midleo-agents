import os
import platform
import re
import sys
import threading
import time
from datetime import datetime

from modules.base import secrets

LOG_DIR = os.path.join(os.getcwd(), "logs")
AGENT_LOG = os.path.join(LOG_DIR, "midleoagent.log")
try:
    MAX_LOG_BYTES = max(1024, min(100 * 1024 * 1024, int(os.environ.get("MIDLEO_MAX_LOG_BYTES", str(5 * 1024 * 1024)))))
except (TypeError, ValueError):
    MAX_LOG_BYTES = 5 * 1024 * 1024
MAX_LOG_LINE_BYTES = 8192
_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
LOG_LEVEL = _LEVELS.get(os.environ.get("MIDLEO_LOG_LEVEL", "INFO").upper(), 20)
_LOG_LOCK = threading.Lock()
_READY_LOG_DIR = None
_HARDENED_PATHS = set()
_LAST_LOG_ERROR = None
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")


def _safe_text(value):
    text = str(value)
    truncated = len(text) > MAX_LOG_LINE_BYTES
    text = secrets.redact_text(text[:MAX_LOG_LINE_BYTES])
    text = _CONTROL_RE.sub(lambda match: "\\x%02x" % ord(match.group()), text)
    return text + (" [truncated]" if truncated else "")


def log_timestamp():
    return datetime.now().astimezone().isoformat(sep=" ", timespec="milliseconds")


def log_enabled(level="INFO"):
    return _LEVELS.get(str(level).upper(), 20) >= LOG_LEVEL


def _ensure_log_dir():
    global _READY_LOG_DIR
    if _READY_LOG_DIR == LOG_DIR:
        return
    os.makedirs(LOG_DIR, mode=0o700, exist_ok=True)
    try:
        os.chmod(LOG_DIR, 0o700)
    except Exception:
        pass
    _READY_LOG_DIR = LOG_DIR


def _rotate_log(path, incoming_bytes=0):
    try:
        size = os.stat(path).st_size
        if size and size + incoming_bytes > MAX_LOG_BYTES:
            os.replace(path, path + ".1")
            _HARDENED_PATHS.discard(path)
    except FileNotFoundError:
        pass


def _write_log(path, line):
    global _READY_LOG_DIR
    payload = (line + "\n").encode("utf-8", errors="backslashreplace")
    with _LOG_LOCK:
        _ensure_log_dir()
        _rotate_log(path, len(payload))
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0)
        try:
            fd = os.open(path, flags, 0o600)
        except FileNotFoundError:
            _READY_LOG_DIR = None
            _ensure_log_dir()
            fd = os.open(path, flags, 0o600)
        try:
            if path not in _HARDENED_PATHS:
                try:
                    os.chmod(path, 0o600)
                except OSError:
                    pass
                if len(_HARDENED_PATHS) < 128:
                    _HARDENED_PATHS.add(path)
            while payload:
                written = os.write(fd, payload)
                if written <= 0:
                    raise OSError("Unable to append log record")
                payload = payload[written:]
        finally:
            os.close(fd)


def Log(logdata, level="INFO", component="agent"):
    global _LAST_LOG_ERROR
    level = str(level).upper()
    if level not in _LEVELS:
        level = "INFO"
    if not log_enabled(level):
        return False
    try:
        component = re.sub(r"[^A-Za-z0-9_.-]", "_", str(component))[:32] or "agent"
        line = log_timestamp() + " " + level + " [" + component + "] " + _safe_text(logdata)
        limit = min(MAX_LOG_LINE_BYTES, MAX_LOG_BYTES - 1)
        encoded = line.encode("utf-8", errors="backslashreplace")
        if len(encoded) > limit:
            line = encoded[:limit - 12].decode("utf-8", errors="ignore") + " [truncated]"
        _write_log(AGENT_LOG, line)
        return True
    except Exception as err:
        now = time.monotonic()
        if _LAST_LOG_ERROR is None or now - _LAST_LOG_ERROR >= 60:
            _LAST_LOG_ERROR = now
            try:
                sys.stderr.write(log_timestamp() + " WARNING [logging] Unable to write agent log (" + type(err).__name__ + ")\n")
            except Exception:
                pass
        return False


def ClearLog():
    return Log("Service started")
    
def Err(logdata):
    text = str(logdata)
    prefix, separator, message = text.partition(":")
    level = {"info": "INFO", "warn": "WARNING", "warning": "WARNING", "error": "ERROR", "exception": "ERROR"}.get(prefix.lower())
    return Log(message.lstrip() if separator and level else text, level or "ERROR")

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
    def __init__(self, uid, groupid, agtver, updint, hw, net, certs):
        self.uid = uid
        self.groupid = groupid
        self.agtver = agtver
        self.updint = updint
        self.hw_info = hw
        self.net_info = net
        self.certs = certs

def WriteData(logdata,logfile):
    now = datetime.now()
    current_time = now.strftime("%Y-%m-%d %H:%M:%S")
    safe_name = os.path.basename(logfile)
    path = os.path.join(LOG_DIR, safe_name)
    _write_log(path, current_time + "," + str(logdata))
