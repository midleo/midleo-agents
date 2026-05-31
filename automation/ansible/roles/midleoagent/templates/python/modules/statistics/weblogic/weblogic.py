import json
import os
import socket
import subprocess
import uuid
from datetime import datetime, timezone

from modules.base import classes, makerequest
from modules.statistics import common


OPTADVISOR_SCHEMA_VERSION = "1.0"
OPTADVISOR_COLLECTOR_NAME = "weblogic-jmx-collector"
OPTADVISOR_COLLECTOR_VERSION = "1.0.0"
OPTADVISOR_TECHNOLOGY = "weblogic"
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
    "docker",
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


def _get_appserver(config, thisnode):
    return config.get("managed_server") or config.get("appserver") or thisnode


def _optadvisor_log_path(thisnode):
    return os.path.join(os.getcwd(), "logs", "weblogic_" + str(thisnode) + "_optadvisor.jsonl")


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


def _normalize_target(thisnode, java_result, resources):
    target = java_result.get("target", {})
    if not isinstance(target, dict):
        target = {}
    target = dict(target)
    if not _safe_text(target.get("server_name")):
        target["server_name"] = thisnode
    status = _safe_text(target.get("status")).lower()
    if status in ("", "unknown") and resources:
        resource_statuses = [
            _safe_text(resource.get("status")).lower()
            for resource in resources
            if isinstance(resource, dict)
        ]
        target["status"] = "running" if "running" in resource_statuses else "connected"
    return target


def buildOptAdvisorPayload(thisnode, config, java_result, collected_at=None):
    if not _optadvisor_enabled(config):
        return None
    if not isinstance(java_result, dict):
        classes.Err("weblogic optadvisor returned invalid collector result")
        return None
    if java_result.get("error") == "yes":
        errorlog = java_result.get("errorlog") or java_result.get("log") or java_result.get("err") or "unknown collector error"
        classes.Err("weblogic optadvisor collector error:" + str(errorlog)[-common.MAX_LOG_BYTES:])
        return None

    appcode = _safe_text(config.get("appcode"))
    server_id = _safe_text(_get_server_id(config, thisnode))
    if not server_id:
        classes.Err("weblogic optadvisor disabled for missing server_id")
        return None

    resources = java_result.get("resources", [])
    if not isinstance(resources, list) or len(resources) == 0:
        classes.Err("weblogic optadvisor returned no resources")
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
            "execution_id": "weblogic-" + node_id + "-" + uuid.uuid4().hex[:21],
            "type": "local",
            "execution_host": socket.gethostname(),
        },
        "target": _normalize_target(thisnode, java_result, resources),
        "resources": resources,
    }


def _collect_optadvisor(thisnode, config, values, jar_path):
    classes.Err("weblogic optadvisor java start:" + str(thisnode))
    java_arg = json.dumps(
        {
            "server": thisnode,
            "appserver": _get_appserver(config, thisnode),
            "function": "getoptadvisor",
            "usr": values["usr"],
            "pwd": values["pwd"],
            "mngmport": values["mngmport"],
            "ssl": values["ssl"],
        }
    )
    command = [
        "java",
        "--add-opens",
        "java.base/java.io=ALL-UNNAMED",
        "-cp",
        "/midleolibs/libs/*:/midleolibs/vendor/*:" + jar_path,
        "midleo_weblogic.weblogic_main",
        java_arg,
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
        classes.Err("weblogic optadvisor timed out after " + str(common.DEFAULT_TIMEOUT_SECONDS) + " seconds")
        return
    except OSError as err:
        classes.Err("weblogic optadvisor failed to start:" + str(err))
        return

    classes.Err("weblogic optadvisor java exit code:" + str(result.returncode))
    if result.stderr:
        classes.Err("weblogic optadvisor Error:" + result.stderr[-common.MAX_LOG_BYTES:])
    if result.returncode != 0:
        classes.Err("weblogic optadvisor failed with exit code " + str(result.returncode))
        return

    try:
        payload_line = _java_payload_line(result.stdout)
        if not payload_line:
            classes.Err("weblogic optadvisor returned no JSON payload")
            return
        java_result = json.loads(payload_line)
        payload = buildOptAdvisorPayload(thisnode, config, java_result, _utc_now())
        if payload is not None:
            _append_optadvisor_payload(thisnode, payload)
    except (json.JSONDecodeError, TypeError, ValueError) as err:
        classes.Err("weblogic optadvisor payload parse error:" + str(err))


def getStat(thisqm, inpdata):
    try:
        inpdata = common.parse_json_object(inpdata)
        values, metrics = common.pop_fields(
            inpdata, {"usr": "", "pwd": "", "mngmport": "", "ssl": "no"}
        )
        optadvisor_config, metrics = _split_optadvisor_config(metrics)
        if common.truthy(optadvisor_config.get("optadvisor_only")):
            metrics = {}
        jar_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "resources",
            "midleo_weblogic.jar",
        )
        if metrics:
            java_arg = json.dumps(
                {
                    "logdir": common.first_value(metrics),
                    "server": thisqm,
                    "mbean": ",".join(metrics.keys()),
                    "function": "getstat",
                    "usr": values["usr"],
                    "pwd": values["pwd"],
                    "mngmport": values["mngmport"],
                    "ssl": values["ssl"],
                }
            )

            common.run_command(
                [
                    "java",
                    "--add-opens",
                    "java.base/java.io=ALL-UNNAMED",
                    "-cp",
                    "/midleolibs/libs/*:/midleolibs/vendor/*:" + jar_path,
                    "midleo_weblogic.weblogic_main",
                    java_arg,
                ],
                "weblogic",
            )

        if common.optadvisor_collection_enabled(optadvisor_config):
            _collect_optadvisor(thisqm, optadvisor_config, values, jar_path)

    except (json.JSONDecodeError, TypeError, ValueError) as err:
        classes.Err("Error in weblogic statistics:" + str(err))


def flushOptAdvisorTelemetry(thisnode, website, webssl, inttoken, thisdata):
    if not isinstance(thisdata, dict):
        return
    optadvisor_config, _ = _split_optadvisor_config(thisdata)
    if not common.optadvisor_enabled(optadvisor_config):
        classes.Err("weblogic optadvisor flush skipped disabled")
        return

    file = _optadvisor_log_path(thisnode)
    if not os.path.isfile(file):
        classes.Err("weblogic optadvisor flush skipped no payload file:" + file)
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
                    status = "no-response" if res is None else str(res.status_code)
                    body = "" if res is None else str(res.text)[-common.MAX_LOG_BYTES:]
                    classes.Err("weblogic optadvisor post failed status:" + status + " body:" + body)
                    remaining.append(line)
                else:
                    classes.Err("weblogic optadvisor post success status:" + str(res.status_code))
            except (json.JSONDecodeError, TypeError, ValueError) as err:
                classes.Err("weblogic optadvisor payload parse error:" + str(err))
            except Exception as err:
                classes.Err("weblogic optadvisor post error:" + str(err))
                remaining.append(line)

        with open(file, "w", encoding="utf-8") as f:
            f.writelines(remaining)
    except OSError as err:
        classes.Err("weblogic optadvisor file error:" + str(err))


def resetStat(thisnode, website, webssl, inttoken, stat_data):
    _, legacy_stat_data = _split_optadvisor_config(stat_data if isinstance(stat_data, dict) else {})
    common.post_csv_stats(
        "weblogic",
        "weblogic",
        website,
        webssl,
        inttoken,
        legacy_stat_data,
        lambda logdir, subtype: logdir + "Statistics_" + subtype + ".csv",
    )
    flushOptAdvisorTelemetry(thisnode, website, webssl, inttoken, stat_data)
