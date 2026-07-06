import json
import os
import time
import uuid

from modules.base import classes
from modules.message_backup import envelope as envelope_mod

DEFAULT_OUTBOX_DIR = os.path.join(os.getcwd(), "data", "message-backup-outbox")


def _ensure_dir(path):
    os.makedirs(path, mode=0o750, exist_ok=True)


def _entry_path(outbox_dir, entry_id):
    return os.path.join(outbox_dir, entry_id + ".json")


def _payload_for_outbox(envelope):
    payload = envelope_mod.envelope_for_submit(envelope)
    body_mode = str(payload.get("body_mode") or "none").lower()
    if body_mode != "full":
        payload["body"] = None
    if body_mode == "none":
        payload["body_sha256"] = None
    return payload


class MessageBackupOutbox:
    def __init__(self, config):
        config = config if isinstance(config, dict) else {}
        self.enabled = bool(config.get("enabled", True))
        self.path = str(config.get("path") or DEFAULT_OUTBOX_DIR)
        self.max_size_mb = int(config.get("max_size_mb", 1024) or 1024)

    def size(self):
        if not os.path.isdir(self.path):
            return 0
        return len([name for name in os.listdir(self.path) if name.endswith(".json")])

    def _trim_if_needed(self):
        if self.max_size_mb <= 0:
            return
        total = 0
        files = []
        for name in os.listdir(self.path):
            if not name.endswith(".json"):
                continue
            full = os.path.join(self.path, name)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            total += size
            files.append((os.path.getmtime(full), full))
        limit = self.max_size_mb * 1024 * 1024
        if total <= limit:
            return
        for _, full in sorted(files):
            try:
                os.remove(full)
            except OSError:
                pass
            total -= os.path.getsize(full) if os.path.exists(full) else 0
            if total <= limit:
                break

    def enqueue(self, envelope, retry_count=0, next_retry_at=None, last_error=""):
        if not self.enabled:
            return False
        _ensure_dir(self.path)
        entry_id = uuid.uuid4().hex
        payload = _payload_for_outbox(envelope)
        record = {
            "id": entry_id,
            "envelope": payload,
            "retry_count": int(retry_count),
            "next_retry_at": next_retry_at or int(time.time()),
            "status": "pending",
            "last_error": str(last_error or "")[:512],
            "created_at": int(time.time()),
        }
        tmp = _entry_path(self.path, entry_id) + ".tmp"
        final = _entry_path(self.path, entry_id)
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, final)
        try:
            os.chmod(final, 0o600)
        except OSError:
            pass
        self._trim_if_needed()
        return True

    def list_due(self, now_ts=None):
        if not self.enabled or not os.path.isdir(self.path):
            return []
        now_ts = int(now_ts or time.time())
        due = []
        for name in sorted(os.listdir(self.path)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(self.path, name)
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    record = json.load(handle)
            except (OSError, json.JSONDecodeError) as err:
                classes.Err("message_backup outbox read failed:" + str(err))
                continue
            if int(record.get("next_retry_at", 0)) <= now_ts:
                record["_path"] = path
                due.append(record)
        return due

    def mark_sent(self, record):
        path = record.get("_path")
        if not path and record.get("id"):
            path = _entry_path(self.path, str(record["id"]))
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError as err:
                classes.Err("message_backup outbox remove failed:" + str(err))

    def mark_retry(self, record, error, delay_seconds):
        path = record.get("_path")
        if not path or not os.path.exists(path):
            return
        record["retry_count"] = int(record.get("retry_count", 0)) + 1
        record["next_retry_at"] = int(time.time()) + max(1, int(delay_seconds))
        record["last_error"] = str(error or "")[:512]
        record["status"] = "pending"
        record.pop("_path", None)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, path)
