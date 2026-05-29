import glob
import json
import os
import socket
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone, timedelta

from modules.base import classes, file_utils, makerequest, statarr

DEFAULT_TIMEOUT_SECONDS = int(os.environ.get("MIDLEO_STAT_TIMEOUT_SECONDS", "45"))
MAX_LOG_BYTES = 4000
MAX_OPTADVISOR_RESOURCES = 250
MAX_OPTADVISOR_ENABLE_DAYS = 30
OPTADVISOR_SCHEMA_VERSION = "1.0"
OPTADVISOR_CONFIG_KEYS = {
    "optadvisor",
    "optadvisor_only",
    "optadvisor_enabled",
    "optimization_advisor",
    "optadvisor_collector_version",
    "optadvisor_technology",
    "appcode",
    "appsrvid",
    "server_id",
    "serverid",
    "srvid",
    "appserver",
    "managed_server",
    "optadvisor_token",
    "optadvisor_token_uid",
    "optadvisor_token_expires_at",
}


def parse_json_object(payload):
    data = json.loads(payload) if isinstance(payload, str) else payload
    if not isinstance(data, dict):
        raise ValueError("statistics input must be a JSON object")
    return data


def pop_fields(data, field_defaults):
    source = dict(data)
    values = {}
    for key, default in field_defaults.items():
        values[key] = source.pop(key, default)
    return values, source


def first_value(data):
    if not data:
        raise ValueError("statistics input has no metrics")
    return next(iter(data.values()))


def run_command(command, label, timeout=DEFAULT_TIMEOUT_SECONDS):
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        classes.Err(label + " timed out after " + str(timeout) + " seconds")
        return False
    except OSError as err:
        classes.Err(label + " failed to start:" + str(err))
        return False

    if result.stdout:
        classes.Err(label + " Output:" + result.stdout[-MAX_LOG_BYTES:])
    if result.stderr:
        classes.Err(label + " Error:" + result.stderr[-MAX_LOG_BYTES:])
    if result.returncode != 0:
        classes.Err(label + " failed with exit code " + str(result.returncode))
        return False
    return True


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso_utc(value=None):
    if value is None:
        value = utc_now()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def truthy(value):
    return str(value).strip().lower() in ("1", "y", "yes", "true", "on", "enabled")


def optadvisor_state_path():
    return os.path.join(os.getcwd(), "config", "optadvisor.json")


def _parse_utc_datetime(value):
    if not value:
        return None
    text = str(value).strip()
    if len(text) >= 19:
        text = text[:19]
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
    return None


def load_optadvisor_runtime_state():
    try:
        with open(optadvisor_state_path(), "r", encoding="utf-8") as f:
            state = json.load(f)
            return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def save_optadvisor_runtime_state(state):
    if not isinstance(state, dict):
        state = {}
    path = optadvisor_state_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_optadvisor_", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            json.dump(state, tmp_file, ensure_ascii=False, indent=2, sort_keys=True)
            tmp_file.write("\n")
        os.replace(tmp_path, path)
        try:
            os.chmod(path, 0o640)
        except Exception:
            pass
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def enable_optadvisor_runtime(days=MAX_OPTADVISOR_ENABLE_DAYS, actor="manual"):
    try:
        duration_days = int(days)
    except (TypeError, ValueError):
        duration_days = MAX_OPTADVISOR_ENABLE_DAYS
    duration_days = max(1, min(duration_days, MAX_OPTADVISOR_ENABLE_DAYS))
    now = utc_now()
    state = {
        "enabled": True,
        "enabled_at": iso_utc(now),
        "expires_at": iso_utc(now + timedelta(days=duration_days)),
        "max_days": MAX_OPTADVISOR_ENABLE_DAYS,
        "requested_days": duration_days,
        "enabled_by": safe_text(actor)[:100] if actor else "manual",
    }
    save_optadvisor_runtime_state(state)
    return state


def disable_optadvisor_runtime(actor="manual", reason="manual"):
    state = load_optadvisor_runtime_state()
    state["enabled"] = False
    state["disabled_at"] = iso_utc()
    state["disabled_by"] = safe_text(actor)[:100] if actor else "manual"
    state["disabled_reason"] = safe_text(reason)[:255] if reason else "manual"
    save_optadvisor_runtime_state(state)
    return state


def optadvisor_runtime_status(now=None):
    if now is None:
        now = utc_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    state = load_optadvisor_runtime_state()
    expires_at = _parse_utc_datetime(state.get("expires_at"))
    configured_enabled = truthy(state.get("enabled"))
    active = configured_enabled and expires_at is not None and expires_at > now
    if active:
        status = "enabled"
    elif configured_enabled and expires_at is not None and expires_at <= now:
        status = "expired"
    else:
        status = "disabled"
    state["status"] = status
    state["active"] = active
    return state


def optadvisor_runtime_enabled(now=None):
    return bool(optadvisor_runtime_status(now).get("active"))


def safe_text(value):
    if value is None:
        return ""
    return str(value).strip().replace("\u0000", "")


def optadvisor_enabled(config):
    return truthy(
        config.get("optadvisor")
        or config.get("optadvisor_enabled")
        or config.get("optimization_advisor")
    )


def optadvisor_collection_enabled(config):
    return optadvisor_enabled(config) and optadvisor_runtime_enabled()


def optadvisor_post_token(config, default_token):
    return safe_text(default_token)


def split_optadvisor_config(data, extra_keys=None):
    config = {}
    metrics = dict(data or {})
    keys = set(OPTADVISOR_CONFIG_KEYS)
    if extra_keys:
        keys.update(extra_keys)
    for key in list(metrics.keys()):
        if key in keys or str(key).startswith("optadvisor_"):
            config[key] = metrics.pop(key)
    return config, metrics


def optadvisor_server_id(config, thisnode):
    return (
        config.get("server_id")
        or config.get("appsrvid")
        or config.get("serverid")
        or config.get("srvid")
        or thisnode
    )


def optadvisor_node_id(thisnode, max_length=24):
    return "".join(ch if ch.isalnum() or ch in ("_", "-", ".") else "-" for ch in str(thisnode))[:max_length]


def optadvisor_log_path(prefix, thisnode):
    return os.path.join(os.getcwd(), "logs", str(prefix) + "_" + str(thisnode) + "_optadvisor.jsonl")


def append_optadvisor_payload(prefix, thisnode, payload):
    os.makedirs(os.path.join(os.getcwd(), "logs"), exist_ok=True)
    with open(optadvisor_log_path(prefix, thisnode), "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n")


def flush_optadvisor_telemetry(prefix, thisnode, website, webssl, inttoken, stat_data, extra_keys=None):
    if not isinstance(stat_data, dict):
        return
    optadvisor_config, _ = split_optadvisor_config(stat_data, extra_keys)
    if not optadvisor_collection_enabled(optadvisor_config):
        classes.Err(prefix + " optadvisor flush skipped disabled")
        return

    file = optadvisor_log_path(prefix, thisnode)
    if not os.path.isfile(file):
        classes.Err(prefix + " optadvisor flush skipped no payload file:" + file)
        return

    remaining = []
    try:
        with open(file, "r", encoding="utf-8") as f:
            lines = [line for line in f if line.strip()]

        for line in lines:
            try:
                payload = json.loads(line)
                payload.pop("inttoken", None)
                res = makerequest.postOptAdvisorTelemetry(
                    webssl,
                    website,
                    payload,
                    optadvisor_post_token(optadvisor_config, inttoken),
                )
                if res is None or res.status_code < 200 or res.status_code >= 300:
                    status = "no-response" if res is None else str(res.status_code)
                    body = "" if res is None else str(res.text)[-MAX_LOG_BYTES:]
                    classes.Err(prefix + " optadvisor post failed status:" + status + " body:" + body)
                    remaining.append(line)
                else:
                    classes.Err(prefix + " optadvisor post success status:" + str(res.status_code))
            except (json.JSONDecodeError, TypeError, ValueError) as err:
                classes.Err(prefix + " optadvisor payload parse error:" + str(err))
            except Exception as err:
                classes.Err(prefix + " optadvisor post error:" + str(err))
                remaining.append(line)

        with open(file, "w", encoding="utf-8") as f:
            f.writelines(remaining)
    except OSError as err:
        classes.Err(prefix + " optadvisor file error:" + str(err))


def java_payload_line(stdout):
    lines = [line.strip() for line in str(stdout or "").splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("{") and line.endswith("}"):
            return line
        if line.startswith("[") and line.endswith("]"):
            return line
    return ""


def build_optadvisor_payload(prefix, technology, collector_name, thisnode, config, target, resources, collected_at=None):
    if not optadvisor_enabled(config):
        return None
    appcode = safe_text(config.get("appcode"))
    server_id = safe_text(optadvisor_server_id(config, thisnode))
    if not appcode or not server_id:
        classes.Err(prefix + " optadvisor disabled for missing appcode or server_id")
        return None
    if not isinstance(resources, list) or len(resources) == 0:
        return None
    if len(resources) > MAX_OPTADVISOR_RESOURCES:
        classes.Err(prefix + " optadvisor resource batch trimmed to " + str(MAX_OPTADVISOR_RESOURCES))
        resources = resources[:MAX_OPTADVISOR_RESOURCES]

    return {
        "schema_version": OPTADVISOR_SCHEMA_VERSION,
        "collected_at": iso_utc(collected_at),
        "appcode": appcode,
        "server_id": server_id,
        "technology": technology,
        "collector": {
            "name": collector_name,
            "version": str(config.get("optadvisor_collector_version") or "1.0.0"),
            "execution_id": prefix + "-" + optadvisor_node_id(thisnode) + "-" + uuid.uuid4().hex[:24],
            "type": "local",
            "execution_host": socket.gethostname(),
        },
        "target": target if isinstance(target, dict) else {},
        "resources": resources,
    }


def metric_number(key, value):
    number = numeric_value(value)
    if number is None:
        return None
    return {"key": key, "value": number, "value_type": "number"}


def metric_string(key, value):
    text = safe_text(value)
    if not text:
        return None
    return {"key": key, "value": text[:255], "value_type": "string"}


def metric_bool(key, value):
    if isinstance(value, bool):
        bool_value = value
    else:
        text = str(value).strip().lower()
        if text in ("1", "true", "yes", "y", "on", "enabled", "started", "running"):
            bool_value = True
        elif text in ("0", "false", "no", "n", "off", "disabled", "stopped"):
            bool_value = False
        else:
            return None
    return {"key": key, "value": bool_value, "value_type": "boolean"}


def add_metric(metrics, metric):
    if metric is not None:
        metrics.append(metric)


def numeric_value(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", "")
    for suffix in ("%", "B/s", "bytes/s", "ms", "s"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    try:
        return float(text)
    except Exception:
        return None


def first_present(data, *keys):
    if not isinstance(data, dict):
        return None
    for key in keys:
        if key in data and data[key] is not None and str(data[key]).strip() != "":
            return data[key]
    return None


def nested(data, *keys):
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def tag_value(metric_key, tag):
    marker = ";" + tag + "="
    if marker not in metric_key:
        return ""
    return metric_key.split(marker, 1)[1].split(";", 1)[0]


def post_csv_stats(stat_type, func_name, website, webssl, inttoken, stat_data, pattern_fn):
    try:
        if not isinstance(stat_data, dict) or len(stat_data) == 0:
            return

        for subtype, logdir in stat_data.items():
            resolved_func_name = func_name(subtype) if callable(func_name) else func_name
            func = getattr(statarr, resolved_func_name, None)
            if func is None:
                classes.Err("Missing stat array for " + stat_type + ":" + resolved_func_name)
                continue

            for file_path in glob.glob(pattern_fn(str(logdir), str(subtype))):
                ret = file_utils.csv_json(file_path, func(), "", True)
                retarr = json.loads(ret)
                if len(retarr) == 0:
                    continue

                payload = {
                    "type": stat_type,
                    "inttoken": inttoken,
                    "subtype": subtype,
                    "data": retarr,
                }
                makerequest.postStatData(webssl, website, json.dumps(payload))

    except OSError as err:
        classes.Err("Error opening the file statlist:" + str(err))
    except (json.JSONDecodeError, TypeError, ValueError) as err:
        classes.Err("Error parsing statlist:" + str(err))
