import json
import os
import socket
import subprocess
import urllib.parse
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


def _normalize_status(value):
    text = _safe_text(value).lower().replace("-", "_").replace(" ", "_")
    if "running" in text:
        return "running"
    if "shutdown" in text or "shutting_down" in text:
        return "shutdown"
    if "admin" in text or "standby" in text:
        return "admin"
    if "failed" in text or "critical" in text:
        return "failed"
    return "unknown"


def _normalize_target(thisnode, java_result, resources):
    target = java_result.get("target", {})
    if not isinstance(target, dict):
        target = {}
    target = dict(target)
    if not _safe_text(target.get("server_name")):
        target["server_name"] = thisnode
    status = _normalize_status(target.get("status"))
    if status == "unknown" and resources:
        resource_statuses = [
            _normalize_status(resource.get("status"))
            for resource in resources
            if isinstance(resource, dict)
        ]
        status = "running" if "running" in resource_statuses else "unknown"
    target["status"] = status
    return target


def _normalize_resources(resources, target):
    target_status = _normalize_status(target.get("status") if isinstance(target, dict) else "")
    if target_status == "unknown":
        return resources

    normalized_resources = []
    for resource in resources:
        if not isinstance(resource, dict):
            continue
        item = dict(resource)
        if item.get("resource_type") == "weblogic_server":
            resource_status = _normalize_status(item.get("status"))
            if resource_status == "unknown":
                item["status"] = target_status
            metrics = []
            has_status_metric = False
            for metric in item.get("metrics", []):
                if not isinstance(metric, dict):
                    continue
                metric_item = dict(metric)
                if metric_item.get("key") == "server_status":
                    has_status_metric = True
                    if _normalize_status(metric_item.get("value")) == "unknown":
                        metric_item["value"] = target_status
                metrics.append(metric_item)
            if not has_status_metric:
                metrics.append({"key": "server_status", "value": target_status, "value_type": "string"})
            item["metrics"] = metrics
        normalized_resources.append(item)
    return normalized_resources


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

    target = _normalize_target(thisnode, java_result, resources)
    resources = _normalize_resources(resources, target)
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
        "target": target,
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


def _weblogic_rest_path(subtype):
    subtype = str(subtype or "").strip()
    paths = {
        "JVMRuntime": "/management/weblogic/latest/serverRuntime/JVMRuntime",
        "ThreadPoolRuntime": "/management/weblogic/latest/serverRuntime/threadPoolRuntime",
        "ConnectorConnectionPoolRuntime": "/management/weblogic/latest/serverRuntime/connectorServiceRuntime/connectorConnectionPoolRuntimeMBeans",
        "JDBCDataSourceRuntime": "/management/weblogic/latest/serverRuntime/JDBCServiceRuntime/JDBCDataSourceRuntimeMBeans",
        "JDBCDataSourceRuntimeMBeans": "/management/weblogic/latest/serverRuntime/JDBCServiceRuntime/JDBCDataSourceRuntimeMBeans",
        "JDBCServiceRuntime": "/management/weblogic/latest/serverRuntime/JDBCServiceRuntime/JDBCDataSourceRuntimeMBeans",
        "ApplicationRuntimes": "/management/weblogic/latest/serverRuntime/applicationRuntimes",
        "ServerRuntime": "/management/weblogic/latest/serverRuntime",
    }
    if subtype.startswith("/"):
        return subtype
    return paths.get(subtype, "")


WEBLOGIC_REST_LEGACY_FIELDS = {
    "JVMRuntime": (
        ("HeapFreeCurrent", ("heapFreeCurrent", "HeapFreeCurrent")),
        ("HeapSizeCurrent", ("heapSizeCurrent", "HeapSizeCurrent")),
        ("HeapFreePercent", ("heapFreePercent", "HeapFreePercent")),
        ("JavaVersion", ("javaVersion", "JavaVersion")),
        ("Uptime", ("uptime", "Uptime")),
    ),
    "ThreadPoolRuntime": (
        ("ExecuteThreadTotalCount", ("executeThreadTotalCount", "ExecuteThreadTotalCount")),
        ("HoggingThreadCount", ("hoggingThreadCount", "HoggingThreadCount")),
        ("PendingUserRequestCount", ("pendingUserRequestCount", "PendingUserRequestCount")),
        ("Throughput", ("throughput", "Throughput")),
    ),
    "ConnectorConnectionPoolRuntime": (
        ("ConnectionsTotalCount", ("connectionsTotalCount", "ConnectionsTotalCount")),
        ("ConnectionsInUseCurrentCount", ("connectionsInUseCurrentCount", "ConnectionsInUseCurrentCount")),
        ("ConnectionsWaitingCurrentCount", ("connectionsWaitingCurrentCount", "ConnectionsWaitingCurrentCount")),
    ),
    "JDBCDataSourceRuntime": (
        ("ActiveConnectionsCurrentCount", ("activeConnectionsCurrentCount", "ActiveConnectionsCurrentCount")),
        ("ActiveConnectionsHighCount", ("activeConnectionsHighCount", "ActiveConnectionsHighCount")),
        ("CurrCapacity", ("currCapacity", "CurrCapacity")),
        ("CurrCapacityHighCount", ("currCapacityHighCount", "CurrCapacityHighCount")),
        ("State", ("state", "State")),
    ),
    "JDBCDataSourceRuntimeMBeans": (
        ("ActiveConnectionsCurrentCount", ("activeConnectionsCurrentCount", "ActiveConnectionsCurrentCount")),
        ("ActiveConnectionsHighCount", ("activeConnectionsHighCount", "ActiveConnectionsHighCount")),
        ("CurrCapacity", ("currCapacity", "CurrCapacity")),
        ("CurrCapacityHighCount", ("currCapacityHighCount", "CurrCapacityHighCount")),
        ("State", ("state", "State")),
    ),
    "ServerRuntime": (
        ("State", ("state", "State")),
        ("OpenSocketsCurrentCount", ("openSocketsCurrentCount", "OpenSocketsCurrentCount")),
        ("ListenPort", ("listenPort", "ListenPort")),
        ("AdminServer", ("adminServer", "AdminServer")),
    ),
}


def _legacy_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _legacy_value(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return "{:,.2f}".format(float(value))
    text = str(value).strip()
    if not text:
        return None
    try:
        return "{:,.2f}".format(float(text))
    except ValueError:
        return text


def _case_value(source, names):
    if not isinstance(source, dict):
        return None
    lower_map = {str(key).lower(): value for key, value in source.items()}
    for name in names:
        if name in source:
            return source[name]
        lowered = str(name).lower()
        if lowered in lower_map:
            return lower_map[lowered]
    return None


def _weblogic_rest_sources(payload):
    items = _weblogic_rest_items(payload)
    return items if items else ([payload] if isinstance(payload, dict) else [])


def _write_legacy_stat_row(logdir, subtype, key, server, timestamp, value):
    formatted = _legacy_value(value)
    if formatted is None:
        return
    os.makedirs(str(logdir), exist_ok=True)
    file_path = os.path.join(str(logdir), "Statistics_" + str(subtype) + ".csv")
    new_file = not os.path.isfile(file_path) or os.path.getsize(file_path) == 0
    with open(file_path, "a", encoding="utf-8", newline="") as f:
        if new_file:
            f.write("key,server,timestamp,value\n")
        f.write(str(key) + "," + str(server) + "," + str(timestamp) + "," + formatted + "\n")


def _write_weblogic_rest_legacy(logdir, subtype, thisnode, payload):
    fields = WEBLOGIC_REST_LEGACY_FIELDS.get(str(subtype))
    if not fields:
        return False
    timestamp = _legacy_timestamp()
    wrote = False
    for source in _weblogic_rest_sources(payload):
        for legacy_name, rest_names in fields:
            value = _case_value(source, rest_names)
            if value is None:
                continue
            _write_legacy_stat_row(logdir, subtype, legacy_name, thisnode, timestamp, value)
            wrote = True
    return wrote


def _collect_rest_statistics(thisnode, values, metrics):
    base_url, _ = common.rest_base_url(thisnode, values, values.get("mngmport") or "7001")
    for subtype, logdir in metrics.items():
        path = _weblogic_rest_path(subtype)
        if not path:
            classes.Err("weblogic rest statistics unsupported subtype:" + str(subtype))
            continue
        try:
            payload = common.rest_json_request(base_url, path, values)
            if not _write_weblogic_rest_legacy(logdir, subtype, thisnode, payload):
                common.write_numeric_tree(logdir, subtype, thisnode, payload)
        except Exception as err:
            classes.Err("weblogic rest statistics error:" + str(err))


def _weblogic_rest_items(payload):
    if not isinstance(payload, dict):
        return []
    for key in ("items", "Items", "result", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = _weblogic_rest_items(value)
            if nested:
                return nested
    return []


def _weblogic_rest_state(payload, appserver):
    if not isinstance(payload, dict):
        return ""
    name = common.safe_text(
        payload.get("name") or payload.get("Name") or payload.get("serverName")
    )
    state = payload.get("state") or payload.get("State") or payload.get("serverState")
    appserver = common.safe_text(appserver)
    if state and (not name or not appserver or name.lower() == appserver.lower()):
        return common.safe_text(state)
    for item in _weblogic_rest_items(payload):
        state = _weblogic_rest_state(item, appserver)
        if state:
            return state
    return ""


def restAvailabilityCheck(thisnode, values):
    appserver = common.safe_text(
        values.get("appserver") or values.get("managed_server") or thisnode
    )
    base_url, _ = common.rest_base_url(thisnode, values, values.get("mngmport") or "7001")
    encoded_server = urllib.parse.quote(appserver, safe="")
    paths = [
        "/management/weblogic/latest/domainRuntime/serverRuntimes/" + encoded_server,
        "/management/weblogic/latest/serverRuntime",
        "/management/weblogic/latest/domainRuntime/serverRuntimes",
    ]
    for path in paths:
        try:
            payload = common.rest_json_request(base_url, path, values)
            state_match = "" if path.endswith("/serverRuntime") else appserver
            state = _weblogic_rest_state(payload, state_match)
            if state.upper() == "RUNNING":
                return 1
        except Exception:
            continue
    return 0


def getStat(thisqm, inpdata):
    try:
        inpdata = common.parse_json_object(inpdata)
        values, metrics = common.pop_fields(
            inpdata,
            {
                "usr": "",
                "pwd": "",
                "mngmport": "",
                "jmxport": "",
                "port": "",
                "webport": "",
                "host": "",
                "ssl": "no",
                "conntype": "jms",
            },
        )
        if not values.get("mngmport"):
            values["mngmport"] = values.get("jmxport") or values.get("port") or values.get("webport") or ""
        optadvisor_config, metrics = _split_optadvisor_config(metrics)
        if common.truthy(optadvisor_config.get("optadvisor_only")):
            metrics = {}
        jar_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "resources",
            "midleo_weblogic.jar",
        )
        if metrics and common.connection_type(values) == "rest":
            _collect_rest_statistics(thisqm, values, metrics)
        elif metrics:
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


def flushOptAdvisorTelemetry(thisnode, website, webssl, _legacy_token, thisdata):
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
                payload.pop("_legacy_token", None)
                res = makerequest.postOptAdvisorTelemetry(webssl, website, payload, common.optadvisor_post_token(optadvisor_config, _legacy_token))
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


def resetStat(thisnode, website, webssl, _legacy_token, stat_data):
    _, legacy_stat_data = _split_optadvisor_config(stat_data if isinstance(stat_data, dict) else {})
    common.post_csv_stats(
        "weblogic",
        "weblogic",
        website,
        webssl,
        _legacy_token,
        legacy_stat_data,
        lambda logdir, subtype: logdir + "Statistics_" + subtype + ".csv",
    )
    flushOptAdvisorTelemetry(thisnode, website, webssl, _legacy_token, stat_data)
