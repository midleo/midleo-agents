import json
import sys
import os
import inspect
import re

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import decrypt, configs, secrets
from modules.message_backup import envelope

DEFAULT_BACKEND = {
    "timeout_ms": 10000,
    "retry": {
        "max_attempts": 5,
        "initial_delay_ms": 1000,
        "max_delay_ms": 60000,
    },
}

DEFAULT_OUTBOX = {
    "enabled": True,
    "path": "data/message-backup-outbox",
    "max_size_mb": 1024,
}
VALID_ACK_AFTER = frozenset({"backend_persisted", "outbox_handoff"})
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

def _bounded_int(data, key, default, minimum, maximum):
    try:
        value = int(data.get(key, default))
    except Exception:
        value = default
    data[key] = min(maximum, max(minimum, value))

def _store_connection_values(data):
    if not isinstance(data, dict):
        return data
    stored = {}
    for key, value in data.items():
        if isinstance(value, dict):
            stored[key] = _store_connection_values(value)
        elif secrets.is_encrypted_secret_key(key) and value:
            if str(key).lower() == "pass" and "pwd" in data:
                continue
            store_key = "pwd" if str(key).lower() == "pass" else str(key)
            stored[store_key] = decrypt.encryptPWD(str(value))
        else:
            store_key = "pwd" if str(key).lower() == "pass" and "pwd" not in data else str(key)
            stored[store_key] = value
    return stored

def _ensure_root(config_data):
    root = _root_config(config_data)
    if not root or root is config_data:
        config_data["message_backup"] = {
            "enabled": False,
            "backend": dict(DEFAULT_BACKEND),
            "outbox": dict(DEFAULT_OUTBOX),
            "brokers": {},
            "jobs": [],
        }
        root = config_data["message_backup"]
    root.setdefault("backend", dict(DEFAULT_BACKEND))
    root.setdefault("outbox", dict(DEFAULT_OUTBOX))
    root.setdefault("brokers", {})
    root.setdefault("jobs", [])
    return root

def _merge_brokers(root, brokers_payload):
    if not isinstance(brokers_payload, dict):
        return
    brokers = root.setdefault("brokers", {})
    for transport, instances in brokers_payload.items():
        transport_key = str(transport).strip().lower()
        if transport_key not in envelope.VALID_TRANSPORTS:
            raise ValueError("unsupported broker transport: " + transport_key)
        if not isinstance(instances, dict):
            continue
        if transport_key not in brokers or not isinstance(brokers.get(transport_key), dict):
            brokers[transport_key] = {}
        for instance, conn in instances.items():
            if not isinstance(conn, dict):
                continue
            existing = dict(brokers[transport_key].get(instance) or {})
            existing.update(_store_connection_values(conn))
            brokers[transport_key][instance] = existing

def add_message_backup():
    job_name = _arg(1, "JOB_NAME")
    if not JOB_NAME_RE.fullmatch(job_name):
        raise ValueError("JOB_NAME may contain only letters, numbers, dot, underscore and dash")
    raw_data = _arg(2, "JOBDATA")

    try:
        job_data = json.loads(raw_data) if raw_data else {}
    except Exception:
        raise ValueError("Invalid JSON for message backup job configuration")

    if not isinstance(job_data, dict):
        raise ValueError("Message backup job configuration must be a JSON object")

    brokers_payload = job_data.pop("brokers", None)
    connection = job_data.pop("connection", None) or job_data.pop("broker", None)

    config_data = configs.getMessageBackupData()
    root = _ensure_root(config_data)

    if brokers_payload:
        _merge_brokers(root, brokers_payload)

    transport = str(job_data.get("transport") or "").strip().lower()
    instance = str(job_data.get("middleware_instance") or "").strip()
    source = str(job_data.get("source") or "").strip()
    if transport not in envelope.VALID_TRANSPORTS:
        raise ValueError("unsupported transport: " + transport)
    if transport == "tibcoems":
        raise ValueError("TIBCO EMS message receive is not implemented")
    if not instance:
        raise ValueError("middleware_instance is required")
    if not source:
        raise ValueError("source is required")

    if isinstance(connection, dict):
        _merge_brokers(root, {transport: {instance: connection}})

    body_mode = str(job_data.get("body_mode", "none")).strip().lower()
    if body_mode not in envelope.VALID_BODY_MODES:
        raise ValueError("body_mode must be one of: " + ",".join(sorted(envelope.VALID_BODY_MODES)))
    ack_after = str(job_data.get("ack_after") or job_data.get("commit_after") or "backend_persisted").strip().lower()
    if ack_after not in VALID_ACK_AFTER:
        raise ValueError("ack_after must be backend_persisted or outbox_handoff")

    job_data["transport"] = transport
    job_data["middleware_instance"] = instance
    job_data["source"] = source
    job_data["body_mode"] = body_mode
    job_data["ack_after"] = ack_after
    job_data["name"] = job_name
    job_data["enabled"] = _as_bool(job_data.get("enabled"), True)
    job_data.pop("interval_seconds", None)
    _bounded_int(job_data, "max_messages", 100, 1, 1000)
    if "batch_size" in job_data and job_data.get("batch_size") is not None:
        _bounded_int(job_data, "batch_size", 50, 1, 1000)
    _bounded_int(job_data, "timeout_ms", 5000, 100, 300000)
    job_data["requeue_on_failure"] = _as_bool(job_data.get("requeue_on_failure"), True)

    jobs = root.get("jobs") if isinstance(root.get("jobs"), list) else []
    updated = False
    for index, job in enumerate(jobs):
        if isinstance(job, dict) and str(job.get("name", "")).strip() == job_name:
            jobs[index] = job_data
            updated = True
            break
    if not updated:
        jobs.append(job_data)
    root["jobs"] = jobs
    root["enabled"] = any(
        isinstance(job, dict) and _as_bool(job.get("enabled"), True) for job in jobs
    )

    configs.saveMessageBackupData(config_data)
    print("Message backup job " + job_name + " has been added")

if __name__ == "__main__":
    add_message_backup()
