import hashlib
import inspect
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from json import JSONDecodeError
from json import JSONDecoder

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import classes, configs, makerequest

MQ_EVENT_QUEUE = os.environ.get("MIDLEO_MQ_EVENT_QUEUE", "SYSTEM.ADMIN.TRACE.ACTIVITY.QUEUE")
MQ_EVENT_WAIT_SECONDS = int(os.environ.get("MIDLEO_MQ_EVENT_WAIT_SECONDS", "1"))
MQ_EVENT_TIMEOUT_SECONDS = int(os.environ.get("MIDLEO_MQ_EVENT_TIMEOUT_SECONDS", "20"))
MQ_EVENT_BATCH_SIZE = int(os.environ.get("MIDLEO_MQ_EVENT_BATCH_SIZE", "250"))
MQ_EVENT_SPOOL_DIR = os.environ.get("MIDLEO_MQ_EVENT_SPOOL_DIR", "/var/lib/midleo/mqtrack/spool")
MQ_SUDO_USER = os.environ.get("MIDLEO_MQ_SUDO_USER", "mqm")
MQ_EVENT_BROWSE = os.environ.get("MIDLEO_MQ_EVENT_BROWSE", "0").strip().lower() in {"1", "true", "yes", "on"}

TRACKED_OPERATIONS = {
    item.strip()
    for item in os.environ.get("MIDLEO_MQ_TRACKED_OPERATIONS", "Put1,Put,Get,Cb,Callback").split(",")
    if item.strip()
}

IGNORED_OBJECTS = {
    item.strip()
    for item in os.environ.get(
        "MIDLEO_MQ_IGNORED_OBJECTS",
        "SYSTEM.ADMIN.TRACE.ACTIVITY.QUEUE,SYSTEM.ADMIN.COMMAND.QUEUE,SYSTEM.DEFAULT.MODEL.QUEUE"
    ).split(",")
    if item.strip()
}

IGNORED_OBJECT_PREFIXES = tuple(
    item.strip()
    for item in os.environ.get(
        "MIDLEO_MQ_IGNORED_OBJECT_PREFIXES",
        "SYSTEM.,AMQ.,PYMQPCF.,PYMQIPCF."
    ).split(",")
    if item.strip()
)

IGNORED_FORMATS = {
    item.strip()
    for item in os.environ.get("MIDLEO_MQ_IGNORED_FORMATS", "MQADMIN").split(",")
    if item.strip()
}

def _ignored_queue_name(name):
    name = _name_value(name)

    if not name:
        return True

    if name in IGNORED_OBJECTS:
        return True

    return name.startswith(IGNORED_OBJECT_PREFIXES)

def _ignored_activity(act):
    if _name_value(act.get("formatName")) in IGNORED_FORMATS:
        return True

    names = [
        act.get("objectName"),
        act.get("resolvedQueueName"),
        act.get("resolvedLocalQueueName"),
        act.get("replyToQueue"),
    ]

    for name in names:
        value = _name_value(name)
        if value and _ignored_queue_name(value):
            return True

    return False
    
def _amqsevt_path():
    candidates = []

    configured = os.environ.get("AMQSEVT", "").strip()
    if configured:
        candidates.append(configured)

    candidates.extend([
        "/opt/mqm/samp/bin/amqsevt",
        "/opt/mqm/bin/amqsevt",
    ])

    for candidate in candidates:
        if os.path.isabs(candidate):
            path = candidate
        else:
            path = shutil.which(candidate)

        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path

    raise RuntimeError("amqsevt executable not found")


def _json_values(output):
    decoder = JSONDecoder()
    index = 0
    values = []

    while index < len(output):
        while index < len(output) and output[index].isspace():
            index += 1

        if index >= len(output):
            break

        value, index = decoder.raw_decode(output, index)

        if isinstance(value, list):
            values.extend(item for item in value if isinstance(item, dict))
        elif isinstance(value, dict):
            values.append(value)

    return values


def _name_value(value, default=""):
    if isinstance(value, dict):
        if value.get("name") is not None:
            return str(value.get("name"))
        if value.get("value") is not None:
            return str(value.get("value"))
        return default

    if value is None:
        return default

    return str(value)


def _hex_value(value):
    if not isinstance(value, str):
        return ""

    value = value.strip()

    if not value:
        return ""

    if len(value) % 2 != 0:
        return ""

    try:
        bytes.fromhex(value)
    except ValueError:
        return ""

    return value.lower()


def _canonical_hash(record):
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _run_mq_event(qmgr):
    cmd = [
        "sudo",
        "-n",
        "-u",
        MQ_SUDO_USER,
        _amqsevt_path(),
        "-m",
        str(qmgr),
        "-q",
        MQ_EVENT_QUEUE,
        "-w",
        str(MQ_EVENT_WAIT_SECONDS),
        "-o",
        "json",
    ]

    if MQ_EVENT_BROWSE:
        cmd.append("-b")

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=MQ_EVENT_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        classes.Err("amqsevt timed out for " + str(qmgr))
        return []

    output = proc.stdout.decode(errors="replace")

    if proc.returncode != 0:
        classes.Err("amqsevt failed for " + str(qmgr) + ": " + output[-2000:])
        return []

    if not output.strip():
        return []

    try:
        return _json_values(output)
    except JSONDecodeError:
        classes.Err("amqsevt returned invalid JSON for " + str(qmgr) + ": " + output[-2000:])
        return []


def _track_records(qmgr, events):
    for event in events:
        event_data = event.get("eventData") or {}

        app = _name_value(event_data.get("applName"))
        channel_name = _name_value(event_data.get("channelName"), "Local")
        connection_name = _name_value(event_data.get("connectionName"), "Local")

        activity_trace = event_data.get("activityTrace") or []

        for act in activity_trace:
            if not isinstance(act, dict):
                continue

            operation_id = _name_value(act.get("operationId"))
            object_name = _name_value(act.get("objectName"))

            if operation_id not in TRACKED_OPERATIONS:
               continue

            if _ignored_activity(act):
               continue

            message_data = _hex_value(act.get("messageData"))

            if message_data:
               act["messageData"] = message_data
            elif "messageData" in act:
               act.pop("messageData", None)

            record = {
                "qmgr": str(qmgr),
                "objectName": object_name,
                "applName": app,
                "channelName": channel_name,
                "connectionName": connection_name,
                "trackdata": act,
            }

            record["trackHash"] = _canonical_hash(record)

            yield record


def _chunks(items, size):
    batch = []

    for item in items:
        batch.append(item)

        if len(batch) >= size:
            yield batch
            batch = []

    if batch:
        yield batch


def _spool_path():
    os.makedirs(MQ_EVENT_SPOOL_DIR, mode=0o750, exist_ok=True)
    return os.path.join(
        MQ_EVENT_SPOOL_DIR,
        str(int(time.time() * 1000)) + "-" + uuid.uuid4().hex + ".json",
    )


def _spool_write(batch):
    path = _spool_path()
    tmp_path = path + ".tmp"

    with open(tmp_path, "w", encoding="utf-8") as handler:
        json.dump({"records": batch}, handler, separators=(",", ":"), ensure_ascii=False)

    os.replace(tmp_path, path)

    return path


def _post_file(path, webssl, website):
    with open(path, "r", encoding="utf-8") as handler:
        payload = handler.read()

    makerequest.postTrackData(webssl, website, payload)
    os.remove(path)


def _flush_spool(webssl, website):
    if not os.path.isdir(MQ_EVENT_SPOOL_DIR):
        return

    for name in sorted(os.listdir(MQ_EVENT_SPOOL_DIR)):
        if not name.endswith(".json"):
            continue

        path = os.path.join(MQ_EVENT_SPOOL_DIR, name)

        try:
            _post_file(path, webssl, website)
        except Exception as err:
            classes.Err("MQ track spool flush failed: " + str(err))
            return


def _send_batch(batch, webssl, website):
    path = _spool_write(batch)
    _post_file(path, webssl, website)


def main():
    track_data = configs.gettrackData()
    config_data = configs.getcfgData()

    website = config_data["MWADMIN"]
    webssl = config_data["SSLENABLED"]

    _flush_spool(webssl, website)

    for qmgr in track_data.keys():
        events = _run_mq_event(qmgr)
        records = _track_records(qmgr, events)

        for batch in _chunks(records, MQ_EVENT_BATCH_SIZE):
            try:
                _send_batch(batch, webssl, website)
            except Exception as err:
                classes.Err("MQ track post failed for " + str(qmgr) + ": " + str(err))

    _flush_spool(webssl, website)


try:
    main()
except Exception as err:
    classes.Err("MQ activity tracking failed: " + str(err))