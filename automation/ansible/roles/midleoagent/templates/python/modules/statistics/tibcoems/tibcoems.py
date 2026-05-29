import json
import os
import socket
import subprocess
import uuid
from datetime import datetime, timezone

from modules.base import classes, makerequest
from modules.statistics import common


OPTADVISOR_SCHEMA_VERSION = "1.0"
OPTADVISOR_COLLECTOR_NAME = "tibcoems-admin-collector"
OPTADVISOR_COLLECTOR_VERSION = "1.0.0"
OPTADVISOR_TECHNOLOGY = "tibcoems"
OPTADVISOR_CONFIG_KEYS = {
    "optadvisor",
    "optadvisor_enabled",
    "optimization_advisor",
    "optadvisor_collector_version",
    "optadvisor_resource_limit",
    "appcode",
    "appsrvid",
    "server_id",
    "serverid",
    "srvid",
    "host",
    "port",
    "tibcosrv",
    "tibcoport",
    "tibcousr",
    "tibcopass",
    "usr",
    "pwd",
    "ssl",
    "sslkey",
    "sslcipher",
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
    return os.path.join(os.getcwd(), "logs", "tibcoems_" + str(thisnode) + "_optadvisor.jsonl")


def _append_optadvisor_payload(thisnode, payload):
    os.makedirs(os.path.join(os.getcwd(), "logs"), exist_ok=True)
    with open(_optadvisor_log_path(thisnode), "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n")


def _java_payload_line(stdout):
    lines = [line.strip() for line in str(stdout or "").splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("{") and line.endswith("}"):
            return line
    return ""


def buildOptAdvisorPayload(thisnode, config, java_result, collected_at=None):
    if not _optadvisor_enabled(config):
        return None
    if not isinstance(java_result, dict) or java_result.get("err") == "yes" or java_result.get("error") == "yes":
        return None

    appcode = _safe_text(config.get("appcode"))
    server_id = _safe_text(_get_server_id(config, thisnode))
    if not appcode or not server_id:
        classes.Err("tibcoems optadvisor disabled for missing appcode or server_id")
        return None

    resources = java_result.get("resources", [])
    if not isinstance(resources, list) or len(resources) == 0:
        return None

    node_id = "".join(ch if ch.isalnum() or ch in ("_", "-", ".") else "-" for ch in str(thisnode))[:24]
    return {
        "schema_version": OPTADVISOR_SCHEMA_VERSION,
        "collected_at": _iso_utc(collected_at),
        "appcode": appcode,
        "server_id": server_id,
        "technology": OPTADVISOR_TECHNOLOGY,
        "collector": {
            "name": OPTADVISOR_COLLECTOR_NAME,
            "version": str(config.get("optadvisor_collector_version") or OPTADVISOR_COLLECTOR_VERSION),
            "execution_id": "tibcoems-" + node_id + "-" + uuid.uuid4().hex[:20],
            "type": "local",
            "execution_host": socket.gethostname(),
        },
        "target": java_result.get("target", {}),
        "resources": resources,
    }


def _int_limit(value):
    try:
        return max(1, min(240, int(value)))
    except Exception:
        return 200


def _java_arg(thisnode, config, values):
    host = values.get("tibcosrv") or values.get("host") or config.get("tibcosrv") or config.get("host") or thisnode
    port = values.get("tibcoport") or values.get("port") or config.get("tibcoport") or config.get("port") or "7222"
    user = values.get("tibcousr") or values.get("usr") or config.get("tibcousr") or config.get("usr") or ""
    password = values.get("tibcopass") or values.get("pwd") or config.get("tibcopass") or config.get("pwd") or ""
    payload = {
        "type": "OPTADVISOR",
        "tibcosrv": host,
        "tibcoport": str(port),
        "ssl": values.get("ssl") or config.get("ssl") or "no",
        "optadvisorlimit": _int_limit(config.get("optadvisor_resource_limit") or values.get("optadvisor_resource_limit") or 200),
    }
    if user:
        payload["tibcousr"] = user
    if password:
        payload["tibcopass"] = password
    sslkey = values.get("sslkey") or config.get("sslkey")
    sslcipher = values.get("sslcipher") or config.get("sslcipher")
    if sslkey:
        payload["sslkey"] = sslkey
    if sslcipher:
        payload["sslcipher"] = sslcipher
    return json.dumps(payload)


def _collect_optadvisor(thisnode, config, values, jar_path):
    command = [
        "java",
        "-cp",
        "/midleolibs/vendor/*:/midleolibs/libs/*:" + jar_path,
        "midleo_tibco.tib_main",
        _java_arg(thisnode, config, values),
        "{}",
    ]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=common.DEFAULT_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        classes.Err("tibcoems optadvisor timed out after " + str(common.DEFAULT_TIMEOUT_SECONDS) + " seconds")
        return
    except OSError as err:
        classes.Err("tibcoems optadvisor failed to start:" + str(err))
        return

    if result.stderr:
        classes.Err("tibcoems optadvisor Error:" + result.stderr[-common.MAX_LOG_BYTES:])
    if result.returncode != 0:
        classes.Err("tibcoems optadvisor failed with exit code " + str(result.returncode))
        return

    try:
        payload_line = _java_payload_line(result.stdout)
        if not payload_line:
            classes.Err("tibcoems optadvisor returned no JSON payload")
            return
        java_result = json.loads(payload_line)
        payload = buildOptAdvisorPayload(thisnode, config, java_result, _utc_now())
        if payload is not None:
            _append_optadvisor_payload(thisnode, payload)
    except (json.JSONDecodeError, TypeError, ValueError) as err:
        classes.Err("tibcoems optadvisor payload parse error:" + str(err))


def getStat(thisnode, inpdata):
    try:
        inpdata = common.parse_json_object(inpdata)
        values, metrics = common.pop_fields(
            inpdata,
            {
                "tibcousr": "",
                "tibcopass": "",
                "usr": "",
                "pwd": "",
                "host": "",
                "port": "7222",
                "tibcosrv": "",
                "tibcoport": "",
                "ssl": "no",
                "sslkey": "",
                "sslcipher": "",
                "optadvisor_resource_limit": "",
            },
        )
        optadvisor_config, _ = _split_optadvisor_config(metrics)
        for key in ("host", "port", "tibcosrv", "tibcoport", "ssl", "sslkey", "sslcipher"):
            if values.get(key):
                optadvisor_config[key] = values[key]
        if common.optadvisor_collection_enabled(optadvisor_config):
            jar_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "resources",
                "midleo_tibco.jar",
            )
            _collect_optadvisor(thisnode, optadvisor_config, values, jar_path)

    except (json.JSONDecodeError, TypeError, ValueError) as err:
        classes.Err("Error in tibcoems statistics:" + str(err))


def flushOptAdvisorTelemetry(thisnode, website, webssl, inttoken, thisdata):
    if not isinstance(thisdata, dict):
        return
    optadvisor_config, _ = _split_optadvisor_config(thisdata)
    if not common.optadvisor_collection_enabled(optadvisor_config):
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
                payload.pop("inttoken", None)
                res = makerequest.postOptAdvisorTelemetry(webssl, website, payload, common.optadvisor_post_token(optadvisor_config, inttoken))
                if res is None or res.status_code < 200 or res.status_code >= 300:
                    remaining.append(line)
            except (json.JSONDecodeError, TypeError, ValueError) as err:
                classes.Err("tibcoems optadvisor payload parse error:" + str(err))
            except Exception as err:
                classes.Err("tibcoems optadvisor post error:" + str(err))
                remaining.append(line)

        with open(file, "w", encoding="utf-8") as f:
            f.writelines(remaining)
    except OSError as err:
        classes.Err("tibcoems optadvisor file error:" + str(err))


def resetStat(thisnode, website, webssl, inttoken, stat_data):
    flushOptAdvisorTelemetry(thisnode, website, webssl, inttoken, stat_data)
