import json
import os
import threading

from modules.base import classes

_COUNTERS = {
    "message_backup_checked": 0,
    "message_backup_received": 0,
    "message_backup_sent_to_backend": 0,
    "message_backup_batches_sent_to_backend": 0,
    "message_backup_persisted": 0,
    "message_backup_duplicate": 0,
    "message_backup_acked": 0,
    "message_backup_nacked": 0,
    "message_backup_backend_delivery_failed": 0,
    "message_backup_broker_connection_failed": 0,
    "message_backup_config_invalid": 0,
    "message_backup_outbox_size": 0,
    "message_backup_outbox_retry_count": 0,
}
_LOCK = threading.Lock()
_METRICS_FILE = os.path.join(os.getcwd(), "config", "message_backup_metrics.json")
_LAST_FLUSH = None


def increment(name, amount=1):
    with _LOCK:
        _COUNTERS[name] = int(_COUNTERS.get(name, 0)) + int(amount)


def set_gauge(name, value):
    with _LOCK:
        _COUNTERS[name] = int(value)


def snapshot():
    with _LOCK:
        return dict(_COUNTERS)


def flush():
    global _LAST_FLUSH
    try:
        data = snapshot()
        if _LAST_FLUSH is None:
            try:
                with open(_METRICS_FILE, "r", encoding="utf-8") as handle:
                    _LAST_FLUSH = json.load(handle)
            except (OSError, ValueError):
                pass
        if data == _LAST_FLUSH and os.path.isfile(_METRICS_FILE):
            return
        tmp = _METRICS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, separators=(",", ":"))
        os.replace(tmp, _METRICS_FILE)
        _LAST_FLUSH = data
    except Exception as err:
        classes.Err("message_backup metrics flush failed:" + str(err))
