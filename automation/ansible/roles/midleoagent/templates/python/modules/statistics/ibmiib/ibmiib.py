import json
import os
import socket
import subprocess
import uuid
from datetime import datetime, timezone

from modules.base import classes, makerequest
from modules.statistics import common


OPTADVISOR_SCHEMA_VERSION = "1.0"
OPTADVISOR_COLLECTOR_NAME = "ibmiib-integration-api-collector"
OPTADVISOR_COLLECTOR_VERSION = "1.0.0"
OPTADVISOR_TECHNOLOGY = "ibmiib"
OPTADVISOR_CONFIG_KEYS = {
    "optadvisor",
    "optadvisor_enabled",
    "optimization_advisor",
    "optadvisor_collector_version",
    "appcode",
    "appsrvid",
    "server_id",
    "serverid",
    "srvid",
    "host",
    "port",
    "server",
    "execution_group",
    "usr",
    "pwd",
    "srvuser",
    "srvpass",
    "ssl",
    "sslenabled",
    "monitoring_mode",
    "optadvisor_monitoring_mode",
}


def _utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso_utc(value):
    if value is None:
        value = _utc_now()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _truthy(value):
    return str(value).strip().lower() in ("1", "y", "yes", "true", "on", "enabled")


def _safe_text(value):
    if value is None:
        return ""
    return str(value).strip().replace("\u0000", "")


def _optadvisor_enabled(config):
    return _truthy(
        config.get("optadvisor")
        or config.get("optadvisor_enabled")
        or config.get("optimization_advisor")
    )


def _split_optadvisor_config(data):
    config = {}
    metrics = dict(data)
    for key in list(metrics.keys()):
        if key in OPTADVISOR_CONFIG_KEYS or str(key).startswith("optadvisor_"):
            config[key] = metrics.pop(key)
    return config, metrics


def _get_server_id(config, thisnode):
    return (
        config.get("server_id")
        or config.get("appsrvid")
        or config.get("serverid")
        or config.get("srvid")
        or thisnode
    )


def _optadvisor_log_path(thisnode):
    return os.path.join(os.getcwd(), "logs", "ibmiib_" + str(thisnode) + "_optadvisor.jsonl")


def _append_optadvisor_payload(thisnode, payload):
    os.makedirs(os.path.join(os.getcwd(), "logs"), exist_ok=True)
    file = _optadvisor_log_path(thisnode)
    with open(file, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n")
    classes.Err("ibmiib optadvisor payload queued:" + file)


def _java_payload_line(stdout):
    lines = [line.strip() for line in str(stdout or "").splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("{") and line.endswith("}"):
            return line
    return ""


def _java_result_error(java_result):
    if not isinstance(java_result, dict):
        return "invalid java result"
    message = (
        java_result.get("errorlog")
        or java_result.get("log")
        or java_result.get("message")
        or java_result.get("error")
        or java_result.get("err")
        or "unknown error"
    )
    return _safe_text(message)[:common.MAX_LOG_BYTES]


def buildOptAdvisorPayload(thisnode, config, java_result, collected_at=None):
    if not _optadvisor_enabled(config):
        return None
    if not isinstance(java_result, dict) or java_result.get("err") == "yes" or java_result.get("error") == "yes":
        classes.Err("ibmiib optadvisor collector error:" + _java_result_error(java_result))
        return None

    server_id = _safe_text(_get_server_id(config, thisnode))
    if not server_id:
        classes.Err("ibmiib optadvisor disabled for missing server_id")
        return None

    resources = java_result.get("resources", [])
    if not isinstance(resources, list) or len(resources) == 0:
        classes.Err("ibmiib optadvisor skipped no resources")
        return None

    node_id = "".join(ch if ch.isalnum() or ch in ("_", "-", ".") else "-" for ch in str(thisnode))[:24]
    payload = {
        "schema_version": OPTADVISOR_SCHEMA_VERSION,
        "collected_at": _iso_utc(collected_at),
        "server_id": server_id,
        "technology": OPTADVISOR_TECHNOLOGY,
        "collector": {
            "name": OPTADVISOR_COLLECTOR_NAME,
            "version": str(config.get("optadvisor_collector_version") or OPTADVISOR_COLLECTOR_VERSION),
            "execution_id": "ibmiib-" + node_id + "-" + uuid.uuid4().hex[:22],
            "type": "local",
            "execution_host": socket.gethostname(),
        },
        "target": java_result.get("target", {}),
        "resources": resources,
    }
    return payload


def _execution_group_filter(thisnode, config, values):
    explicit = _safe_text(values.get("execution_group") or config.get("execution_group"))
    if explicit:
        return explicit

    candidate = _safe_text(values.get("server") or config.get("server"))
    if candidate and candidate.lower() != _safe_text(thisnode).lower():
        return candidate

    return ""


def _java_arg(thisnode, config, values):
    return json.dumps(
        {
            "type": "OPTADVISOR",
            "host": values.get("host") or config.get("host") or thisnode,
            "port": int(values.get("port") or config.get("port") or 4414),
            "node": thisnode,
            "server": _execution_group_filter(thisnode, config, values),
            "usr": values.get("usr", ""),
            "pwd": values.get("pwd", ""),
            "ssl": values.get("ssl") or config.get("ssl") or "no",
        }
    )


def _java_classpath(jar_path):
    return (
        "/midleolibs/vendor/bipbroker.jar:"
        "/midleolibs/vendor/brokerutil.jar:"
        "/midleolibs/vendor/IntegrationAPI_IIB.jar:"
        "/midleolibs/libs/*:"
        + jar_path
    )


def _java_env():
    env = os.environ.copy()
    env["LANG"] = "C"
    env["LC_ALL"] = "C"
    return env


def _collect_optadvisor(thisnode, config, values, jar_path):
    classes.Err("ibmiib optadvisor java start:" + str(thisnode))
    command = [
        "java",
        "-cp",
        _java_classpath(jar_path),
        "midleoiib.midleo_iib_main",
        _java_arg(thisnode, config, values),
    ]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=common.DEFAULT_TIMEOUT_SECONDS,
            check=False,
            env=_java_env(),
        )
    except subprocess.TimeoutExpired:
        classes.Err("ibmiib optadvisor timed out after " + str(common.DEFAULT_TIMEOUT_SECONDS) + " seconds")
        return
    except OSError as err:
        classes.Err("ibmiib optadvisor failed to start:" + str(err))
        return

    classes.Err("ibmiib optadvisor java exit code:" + str(result.returncode))
    if result.stderr:
        classes.Err("ibmiib optadvisor Error:" + result.stderr[-common.MAX_LOG_BYTES:])
    if result.returncode != 0:
        if result.stdout:
            classes.Err("ibmiib optadvisor Output:" + result.stdout[-common.MAX_LOG_BYTES:])
        classes.Err("ibmiib optadvisor failed with exit code " + str(result.returncode))
        return

    try:
        payload_line = _java_payload_line(result.stdout)
        if not payload_line:
            classes.Err("ibmiib optadvisor returned no JSON payload")
            return
        java_result = json.loads(payload_line)
        payload = buildOptAdvisorPayload(thisnode, config, java_result, _utc_now())
        if payload is not None:
            _append_optadvisor_payload(thisnode, payload)
    except (json.JSONDecodeError, TypeError, ValueError) as err:
        classes.Err("ibmiib optadvisor payload parse error:" + str(err))


def getStat(thisqm, inpdata):
    try:
        inpdata = common.parse_json_object(inpdata)
        values, metrics = common.pop_fields(
            inpdata,
            {
                "usr": "",
                "pwd": "",
                "srvuser": "",
                "srvpass": "",
                "host": "",
                "port": "4414",
                "server": "",
                "execution_group": "",
                "ssl": "no",
                "sslenabled": "",
            },
        )
        if not values.get("usr") and values.get("srvuser"):
            values["usr"] = values["srvuser"]
        if not values.get("pwd") and values.get("srvpass"):
            values["pwd"] = values["srvpass"]
        if not values.get("ssl") or values.get("ssl") == "no":
            if str(values.get("sslenabled", "")).strip() in ("1", "yes", "true", "on"):
                values["ssl"] = "yes"
        optadvisor_config, _ = _split_optadvisor_config(metrics)
        if values.get("host"):
            optadvisor_config["host"] = values["host"]
        if values.get("port"):
            optadvisor_config["port"] = values["port"]
        if values.get("server"):
            optadvisor_config["server"] = values["server"]
        if values.get("execution_group"):
            optadvisor_config["execution_group"] = values["execution_group"]
        if common.optadvisor_collection_enabled(optadvisor_config):
            jar_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "resources",
                "midleoiib.jar",
            )
            _collect_optadvisor(thisqm, optadvisor_config, values, jar_path)

    except (json.JSONDecodeError, TypeError, ValueError) as err:
        classes.Err("Error in ibmiib statistics:" + str(err))


def flushOptAdvisorTelemetry(thisnode, website, webssl, _legacy_token, thisdata):
    if not isinstance(thisdata, dict):
        return
    optadvisor_config, _ = _split_optadvisor_config(thisdata)
    if not common.optadvisor_enabled(optadvisor_config):
        return

    file = _optadvisor_log_path(thisnode)
    if not os.path.isfile(file):
        return

    remaining = []
    try:
        with open(file, "r", encoding="utf-8") as f:
            lines = [line for line in f if line.strip()]

        for line in lines:
            try:
                payload = json.loads(line)
                payload.pop("_legacy_token", None)
                res = makerequest.postOptAdvisorTelemetry(webssl, website, payload, common.optadvisor_post_token(optadvisor_config, _legacy_token))
                if not makerequest._optadvisor_post_accepted(res):
                    status = "no-response" if res is None else str(res.status_code)
                    body = "" if res is None else str(res.text)[-common.MAX_LOG_BYTES:]
                    classes.Err("ibmiib optadvisor post failed status:" + status + " body:" + body)
                    remaining.append(line)
                else:
                    classes.Err("ibmiib optadvisor post success status:" + str(res.status_code))
            except (json.JSONDecodeError, TypeError, ValueError) as err:
                classes.Err("ibmiib optadvisor payload parse error:" + str(err))
            except Exception as err:
                classes.Err("ibmiib optadvisor post error:" + str(err))
                remaining.append(line)

        with open(file, "w", encoding="utf-8") as f:
            f.writelines(remaining)
    except OSError as err:
        classes.Err("ibmiib optadvisor file error:" + str(err))


def resetStat(thisnode, website, webssl, _legacy_token, stat_data):
    flushOptAdvisorTelemetry(thisnode, website, webssl, _legacy_token, stat_data)
