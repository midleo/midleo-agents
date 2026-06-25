import base64
import glob
import json
import os
import socket
import subprocess
import tempfile
import time
import ssl as ssl_module
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone, timedelta

from modules.base import classes, decrypt, file_utils, makerequest, secrets, statarr

DEFAULT_TIMEOUT_SECONDS = int(os.environ.get("MIDLEO_STAT_TIMEOUT_SECONDS", "45"))
MAX_LOG_BYTES = 4000
MAX_STAT_PAYLOAD_BYTES = int(os.environ.get("MIDLEO_STAT_PAYLOAD_MAX_BYTES", str(4 * 1024 * 1024)))
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
    "monitoring_mode",
    "optadvisor_monitoring_mode",
    "appcode",
    "appsrvid",
    "server_id",
    "serverid",
    "srvid",
    "appserver",
    "managed_server",
}
REMOVED_OPTADVISOR_AUTH_KEYS = secrets.REMOVED_AUTH_KEYS


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


def rest_verify_enabled(values):
    values = values or {}
    verify_value = None
    for key in ("ssl_verify", "sslverify"):
        if key in values and values.get(key) is not None and str(values.get(key)).strip() != "":
            verify_value = values.get(key)
            break
    if verify_value is None or str(verify_value).strip() == "":
        verify_value = "yes"
    return truthy(verify_value)


def decrypt_password(value):
    if not value:
        return ""
    try:
        return decrypt.decryptPWD(value)
    except Exception:
        return str(value)


def connection_type(values):
    return str((values or {}).get("conntype") or "jms").strip().lower()


def rest_base_url(thisnode, values, default_port=""):
    values = values or {}
    host = safe_text(values.get("host") or thisnode)
    port = safe_text(
        values.get("port")
        or values.get("webport")
        or values.get("mngmport")
        or values.get("jmxport")
        or values.get("soapport")
        or default_port
    )
    use_ssl = truthy(values.get("ssl"))
    scheme = "https" if use_ssl else "http"
    return scheme + "://" + host + (":" + port if port else ""), use_ssl


def rest_json_request(base_url, path, values, method="GET", payload=None, auth="basic"):
    values = values or {}
    url = base_url + path
    usr = safe_text(values.get("usr"))
    pwd = decrypt_password(values.get("pwd") or "")
    use_ssl = url.lower().startswith("https://")
    verify_ssl = rest_verify_enabled(values)
    headers = {
        "Accept": "application/json",
        "X-Requested-By": "Midleo",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if auth == "basic" and usr:
        token = base64.b64encode((usr + ":" + pwd).encode("utf-8")).decode("ascii")
        headers["Authorization"] = "Basic " + token

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    handlers = []
    if auth == "digest" and usr:
        passman = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        passman.add_password(None, url, usr, pwd)
        handlers.append(urllib.request.HTTPDigestAuthHandler(passman))
    if use_ssl and not verify_ssl:
        handlers.append(urllib.request.HTTPSHandler(context=ssl_module._create_unverified_context()))

    if handlers:
        opener = urllib.request.build_opener(*handlers)
        with opener.open(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8", errors="replace")
    else:
        options = {"timeout": DEFAULT_TIMEOUT_SECONDS}
        if use_ssl and not verify_ssl:
            options["context"] = ssl_module._create_unverified_context()
        with urllib.request.urlopen(request, **options) as response:
            body = response.read().decode("utf-8", errors="replace")
    return json.loads(body) if body else {}


def write_stat_row(logdir, subtype, row):
    if not logdir or not subtype or not row:
        return
    os.makedirs(str(logdir), exist_ok=True)
    file_path = os.path.join(str(logdir), "Statistics_" + str(subtype) + ".csv")
    with open(file_path, "a", encoding="utf-8", newline="") as f:
        f.write(",".join(str(item).replace(",", " ") for item in row) + "\n")


def write_simple_stat(logdir, subtype, server, key, value, timestamp=None):
    number = numeric_value(value)
    if number is None:
        return
    if timestamp is None:
        timestamp = iso_utc()
    write_stat_row(logdir, subtype, [key, server, timestamp, number])


def write_numeric_tree(logdir, subtype, server, data, prefix="", timestamp=None, limit=250):
    if timestamp is None:
        timestamp = iso_utc()
    written = 0

    def walk(value, path):
        nonlocal written
        if written >= limit:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                safe_key = safe_text(key)
                if not safe_key:
                    continue
                walk(item, path + "." + safe_key if path else safe_key)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, path + "." + str(index) if path else str(index))
        else:
            number = numeric_value(value)
            if number is not None and path:
                write_stat_row(logdir, subtype, [path, server, timestamp, number])
                written += 1

    walk(data, prefix)
    return written


def optadvisor_state_path():
    return os.path.join(os.getcwd(), "config", "optadvisor.json")


def optadvisor_lock_path(name="runtime"):
    safe_name = "".join(ch if ch.isalnum() or ch in ("_", "-") else "-" for ch in str(name or "runtime"))
    return os.path.join(os.getcwd(), "config", "optadvisor_" + safe_name + ".lock")


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
            os.chmod(path, 0o600)
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


def _lock_stale_seconds(default=1800):
    try:
        value = int(os.environ.get("MIDLEO_OPTADVISOR_LOCK_STALE_SECONDS", str(default)))
    except (TypeError, ValueError):
        value = default
    return max(60, min(value, 86400))


def _lock_is_stale(path, stale_seconds):
    now = time.time()
    created_ts = 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            created_ts = float(data.get("created_ts") or 0)
    except Exception:
        try:
            created_ts = os.path.getmtime(path)
        except OSError:
            created_ts = now
    return created_ts <= 0 or (now - created_ts) > stale_seconds


def acquire_optadvisor_lock(name="runtime", stale_seconds=None):
    if stale_seconds is None:
        stale_seconds = _lock_stale_seconds()
    path = optadvisor_lock_path(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "pid": os.getpid(),
                        "host": socket.gethostname(),
                        "created_at": iso_utc(),
                        "created_ts": time.time(),
                        "name": str(name or "runtime"),
                    },
                    f,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                f.write("\n")
            return {"path": path, "name": str(name or "runtime")}
        except FileExistsError:
            if _lock_is_stale(path, stale_seconds):
                try:
                    os.unlink(path)
                    continue
                except OSError:
                    pass
            return None
        except OSError as err:
            classes.Err("optadvisor lock error:" + str(err))
            return None
    return None


def release_optadvisor_lock(lock):
    if not lock:
        return
    path = lock.get("path") if isinstance(lock, dict) else str(lock)
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except OSError as err:
        classes.Err("optadvisor lock release error:" + str(err))


def optadvisor_run_seconds_limit(default=240):
    try:
        value = int(os.environ.get("MIDLEO_OPTADVISOR_MAX_RUN_SECONDS", str(default)))
    except (TypeError, ValueError):
        value = default
    return max(30, min(value, 3600))


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
    return ""


def split_optadvisor_config(data, extra_keys=None):
    config = {}
    metrics = dict(data or {})
    keys = set(OPTADVISOR_CONFIG_KEYS) | set(REMOVED_OPTADVISOR_AUTH_KEYS)
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


def flush_optadvisor_telemetry(prefix, thisnode, website, webssl, _legacy_token, stat_data, extra_keys=None):
    if not isinstance(stat_data, dict):
        return
    optadvisor_config, _ = split_optadvisor_config(stat_data, extra_keys)
    if not optadvisor_enabled(optadvisor_config):
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
                payload.pop("_legacy_token", None)
                res = makerequest.postOptAdvisorTelemetry(
                    webssl,
                    website,
                    payload,
                    optadvisor_post_token(optadvisor_config, _legacy_token),
                )
                if not makerequest._optadvisor_post_accepted(res):
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
    server_id = safe_text(optadvisor_server_id(config, thisnode))
    if not server_id:
        classes.Err(prefix + " optadvisor disabled for missing server_id")
        return None
    if not isinstance(resources, list) or len(resources) == 0:
        return None
    if len(resources) > MAX_OPTADVISOR_RESOURCES:
        classes.Err(prefix + " optadvisor resource batch trimmed to " + str(MAX_OPTADVISOR_RESOURCES))
        resources = resources[:MAX_OPTADVISOR_RESOURCES]

    payload = {
        "schema_version": OPTADVISOR_SCHEMA_VERSION,
        "collected_at": iso_utc(collected_at),
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
    return payload


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


def _stat_payload_json(stat_type, subtype, data):
    return json.dumps(
        {
            "type": stat_type,
            "subtype": subtype,
            "data": data,
        },
        separators=(",", ":"),
    )


def _stat_payload_size(stat_type, subtype, data):
    return len(_stat_payload_json(stat_type, subtype, data).encode("utf-8"))


def _iter_stat_value_chunks(stat_type, subtype, key, value, max_bytes):
    text = str(value or "")
    points = [point for point in text.split(";") if point]
    if not points:
        yield text
        return

    chunk = ""
    for point in points:
        item = point + ";"
        candidate = chunk + item
        if chunk and _stat_payload_size(stat_type, subtype, {key: candidate}) > max_bytes:
            yield chunk
            chunk = item
        else:
            chunk = candidate

        if _stat_payload_size(stat_type, subtype, {key: chunk}) > max_bytes:
            classes.Err("stat payload single point exceeds byte limit for " + stat_type + ":" + str(subtype))
            yield chunk
            chunk = ""

    if chunk:
        yield chunk


def iter_stat_payload_chunks(stat_type, subtype, data, max_bytes=MAX_STAT_PAYLOAD_BYTES):
    if not isinstance(data, dict) or not data:
        return
    current = {}
    for key, value in data.items():
        candidate = dict(current)
        candidate[key] = value
        if _stat_payload_size(stat_type, subtype, candidate) <= max_bytes:
            current = candidate
            continue

        if current:
            yield current
            current = {}

        single = {key: value}
        if _stat_payload_size(stat_type, subtype, single) <= max_bytes:
            current = single
            continue

        for value_chunk in _iter_stat_value_chunks(stat_type, subtype, key, value, max_bytes):
            yield {key: value_chunk}

    if current:
        yield current


def post_stat_payloads(stat_type, subtype, website, webssl, data):
    chunk_count = 0
    for chunk in iter_stat_payload_chunks(stat_type, subtype, data):
        chunk_count += 1
        res = makerequest.postStatData(webssl, website, _stat_payload_json(stat_type, subtype, chunk))
        if not makerequest._stat_post_accepted(res):
            status = "no-response" if res is None else str(res.status_code)
            body = "" if res is None else str(res.text)[-MAX_LOG_BYTES:]
            classes.Err(
                "stat payload post failed for "
                + stat_type
                + ":"
                + str(subtype)
                + " chunk:"
                + str(chunk_count)
                + " status:"
                + status
                + " body:"
                + body
            )
            return False
    if chunk_count > 1:
        classes.Err("stat payload split for " + stat_type + ":" + str(subtype) + " chunks:" + str(chunk_count))
    return chunk_count > 0


def post_csv_stats(stat_type, func_name, website, webssl, _legacy_token, stat_data, pattern_fn):
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
                ret = file_utils.csv_json(file_path, func(), "", False)
                retarr = json.loads(ret)
                if len(retarr) == 0:
                    file_utils.truncate_file(file_path)
                    continue

                if post_stat_payloads(stat_type, subtype, website, webssl, retarr):
                    file_utils.truncate_file(file_path)
                else:
                    classes.Err("stat upload failed, keeping file for retry:" + str(file_path))

    except OSError as err:
        classes.Err("Error opening the file statlist:" + str(err))
    except (json.JSONDecodeError, TypeError, ValueError) as err:
        classes.Err("Error parsing statlist:" + str(err))
