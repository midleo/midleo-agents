import csv
import glob
import json
import os
import socket
import subprocess
import uuid
from urllib.parse import quote
from datetime import datetime, timezone

import requests
import urllib3

from modules.base import decrypt, file_utils
from modules.base import classes, makerequest
from modules.statistics import common


OPTADVISOR_SCHEMA_VERSION = "1.0"
OPTADVISOR_COLLECTOR_NAME = "ibmace-integration-admin-collector"
OPTADVISOR_COLLECTOR_VERSION = "1.0.0"
OPTADVISOR_TECHNOLOGY = "ibmace"
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
    "integration_server",
    "usr",
    "pwd",
    "srvuser",
    "srvpass",
    "ssl",
    "sslenabled",
    "sslverify",
    "ssl_verify",
    "conntype",
    "mngmport",
    "jmxport",
    "webport",
    "docker",
    "contname",
    "monitoring_mode",
    "optadvisor_monitoring_mode",
}
ACE_REST_CONTAINER_NAMES = {
    "applications",
    "libraries",
    "messageflows",
    "policies",
    "resources",
    "restapis",
    "schemas",
    "services",
    "statistics",
    "subflows",
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
    return os.path.join(os.getcwd(), "logs", "ibmace_" + str(thisnode) + "_optadvisor.jsonl")


def _append_optadvisor_payload(thisnode, payload):
    os.makedirs(os.path.join(os.getcwd(), "logs"), exist_ok=True)
    with open(_optadvisor_log_path(thisnode), "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n")


def _number(value):
    try:
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        return float(text)
    except Exception:
        return None


def _queue_optadvisor_jvm_stats(thisnode, config, legacy_stat_data):
    if not isinstance(legacy_stat_data, dict):
        return
    resources = {}
    target_node = str(thisnode)

    for subtype, logdir in legacy_stat_data.items():
        if str(subtype).lower() != "jvm":
            continue
        pattern = str(logdir) + "ResourceStats_" + str(thisnode) + "_*_" + str(subtype) + ".txt"
        for file_path in glob.glob(pattern):
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore", newline="") as f:
                    for row in csv.reader((line.replace("\0", "") for line in f), delimiter=","):
                        if len(row) <= 9 or row[0] == "ResourceName":
                            continue
                        node_name = _safe_text(row[1])
                        server_name = _safe_text(row[2])
                        used_value = _number(row[7])
                        max_value = _number(row[9])
                        if not server_name or used_value is None:
                            continue
                        target_node = node_name or target_node
                        resource = {
                            "resource_type": "ace_integration_server",
                            "technical_key": server_name,
                            "name": server_name,
                            "status": "running",
                            "metadata": {},
                            "metrics": [
                                {
                                    "key": "memory_used_bytes",
                                    "value": used_value,
                                    "value_type": "number",
                                }
                            ],
                        }
                        if max_value is not None:
                            resource["metadata"]["jvmMaxHeapSize"] = max_value
                        resources[server_name] = resource
            except OSError as err:
                classes.Err("ibmace optadvisor JVM stats read error:" + str(err))

    if not resources:
        return

    payload = buildOptAdvisorPayload(
        thisnode,
        config,
        {
            "target": {
                "status": "connected",
                "server_name": target_node,
                "metadata": {
                    "integration_node": target_node,
                    "source": "resource_stats",
                },
            },
            "resources": list(resources.values()),
        },
        _utc_now(),
    )
    if payload is not None:
        _append_optadvisor_payload(thisnode, payload)


def _java_payload_line(stdout):
    lines = [line.strip() for line in str(stdout or "").splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("{") and line.endswith("}"):
            return line
    return ""


def _rest_verify(config, values):
    for source in (values or {}, config or {}):
        for key in ("ssl_verify", "sslverify"):
            value = source.get(key)
            if value is not None and str(value).strip() != "":
                return common.truthy(value)
    return True


def _rest_password(values):
    pwd = values.get("pwd", "")
    if not pwd:
        return ""
    try:
        return decrypt.decryptPWD(pwd)
    except Exception:
        return str(pwd)


def _rest_base_url(thisnode, config, values):
    host = values.get("host") or config.get("host") or thisnode
    port = values.get("port") or config.get("port") or "4414"
    scheme = "https" if common.truthy(values.get("ssl") or config.get("ssl")) else "http"
    return scheme + "://" + str(host).strip().rstrip("/") + ":" + str(port).strip()


def _rest_get(base_url, path, auth, verify):
    if not verify:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    try:
        response = requests.get(
            base_url.rstrip("/") + path,
            auth=auth,
            headers={"Accept": "application/json"},
            timeout=common.DEFAULT_TIMEOUT_SECONDS,
            verify=verify,
        )
        if response.status_code != 200:
            classes.Err("ibmace optadvisor REST status:" + str(response.status_code) + " path:" + path)
            return {}
        data = response.json()
        return data if isinstance(data, dict) else {}
    except requests.exceptions.RequestException as err:
        classes.Err("ibmace optadvisor REST error:" + str(err))
    except (json.JSONDecodeError, TypeError, ValueError) as err:
        classes.Err("ibmace optadvisor REST parse error:" + str(err))
    return {}


def _children(payload, child_key=None):
    if not isinstance(payload, dict):
        return []
    if child_key and isinstance(payload.get("children"), dict):
        child = payload["children"].get(child_key)
        if isinstance(child, dict):
            children = child.get("children")
            if isinstance(children, list):
                return children
            if isinstance(children, dict):
                return [value for value in children.values() if isinstance(value, dict)]
    if isinstance(payload.get("children"), list):
        return payload["children"]
    if isinstance(payload.get("children"), dict):
        return [value for value in payload["children"].values() if isinstance(value, dict)]
    return []


def _children_reliable(payload, child_key=None):
    if not isinstance(payload, dict):
        return False
    children = payload.get("children")
    if child_key:
        return isinstance(children, dict) and child_key in children
    return "children" in payload or payload.get("hasChildren") is False


def _message_flow_children(payload):
    candidates = _children(payload, "messageflows")
    if not candidates:
        candidates = _children(payload)
    return [item for item in candidates if _is_message_flow(item)]


def _is_message_flow(payload):
    if not isinstance(payload, dict) or not _safe_text(payload.get("name")):
        return False
    name = _safe_text(payload.get("name")).lower()
    if name in ACE_REST_CONTAINER_NAMES:
        return False
    uri = _safe_text(payload.get("uri")).lower()
    if "/messageflows/" in uri:
        return True
    item_type = _safe_text(payload.get("type") or common.first_present(payload.get("properties", {}), "type")).lower()
    if item_type:
        return "messageflow" in item_type or "message flow" in item_type
    return True


def _status_from(payload, default="connected"):
    if not isinstance(payload, dict):
        return default
    for source in (payload, payload.get("properties"), payload.get("active"), payload.get("descriptiveProperties")):
        if isinstance(source, dict):
            status = _safe_text(source.get("status") or source.get("state") or source.get("resourceState"))
            if status:
                return status.lower()
            running = source.get("running")
            if isinstance(running, bool):
                return "running" if running else "stopped"
    return default


def _is_active_flow_status(status):
    normalized = _safe_text(status).lower()
    return normalized in ("running", "started", "active", "statestarted")


def _resource(resource_type, key, name, status, metadata, metrics, parent=None):
    item = {
        "resource_type": resource_type,
        "technical_key": key,
        "name": name,
        "status": status,
        "metadata": metadata if isinstance(metadata, dict) else {},
        "metrics": metrics if isinstance(metrics, list) else [],
    }
    if parent:
        item["parent_technical_key"] = parent
    return item


def _copy_metadata(metadata, source, mappings):
    if not isinstance(metadata, dict) or not isinstance(source, dict):
        return
    for src_key, dst_key in mappings:
        value = source.get(src_key)
        if value not in (None, ""):
            metadata[dst_key] = value


def _rest_collect_optadvisor(thisnode, config, values):
    base_url = _rest_base_url(thisnode, config, values)
    verify = _rest_verify(config, values)
    auth = (values.get("usr", ""), _rest_password(values))
    root = _rest_get(base_url, "/apiv2?depth=2", auth, verify)
    if not root:
        return None

    node_name = _safe_text(root.get("name")) or _safe_text(values.get("host") or config.get("host") or thisnode)
    target = {
        "status": "connected",
        "server_name": node_name,
        "metadata": {
            "integration_node": node_name,
        },
    }
    version = common.first_present(root.get("descriptiveProperties", {}), "version")
    if version:
        target["metadata"]["version"] = str(version)

    resources = []
    servers = _children(root, "servers")
    if not servers:
        servers_payload = _rest_get(base_url, "/apiv2/servers?depth=2", auth, verify)
        servers = _children(servers_payload)

    for server in servers:
        if not isinstance(server, dict) or not _safe_text(server.get("name")):
            continue
        server_name = _safe_text(server.get("name"))
        server_detail = _rest_get(base_url, "/apiv2/servers/" + quote(server_name, safe="") + "?depth=3", auth, verify)
        server_data = server_detail if server_detail else server
        server_status = _status_from(server_data)
        metadata = {}
        properties = server_data.get("properties") if isinstance(server_data.get("properties"), dict) else {}
        active = server_data.get("active") if isinstance(server_data.get("active"), dict) else {}
        _copy_metadata(metadata, properties, (
            ("defaultQueueManager", "default_queue_manager"),
            ("brokerDefaultCCSID", "brokerDefaultCCSID"),
            ("jvmMinHeapSize", "jvmMinHeapSize"),
            ("jvmMaxHeapSize", "jvmMaxHeapSize"),
            ("jvmDebugPort", "jvmDebugPort"),
        ))
        _copy_metadata(metadata, active, (
            ("processId", "process_id"),
            ("monitoring", "monitoring"),
        ))

        apps = _children(server_data, "applications")
        apps_reliable = _children_reliable(server_data, "applications")
        if not apps and not apps_reliable:
            apps_payload = _rest_get(base_url, "/apiv2/servers/" + quote(server_name, safe="") + "/applications?depth=2", auth, verify)
            apps_reliable = _children_reliable(apps_payload)
            apps = _children(apps_payload)
        flow_resources = []
        flow_counts_reliable = apps_reliable
        for app in apps:
            if not isinstance(app, dict) or not _safe_text(app.get("name")):
                continue
            app_name = _safe_text(app.get("name"))
            app_detail = _rest_get(
                base_url,
                "/apiv2/servers/" + quote(server_name, safe="") + "/applications/" + quote(app_name, safe="") + "?depth=3",
                auth,
                verify,
            )
            app_data = app_detail if app_detail else app
            flows = _message_flow_children(app_data)
            flows_reliable = _children_reliable(app_data, "messageflows")
            if not flows and not flows_reliable:
                flows_payload = _rest_get(
                    base_url,
                    "/apiv2/servers/" + quote(server_name, safe="") + "/applications/" + quote(app_name, safe="") + "/messageflows?depth=2",
                    auth,
                    verify,
                )
                flows_reliable = _children_reliable(flows_payload)
                flows = _message_flow_children(flows_payload)
            if not flows_reliable:
                flow_counts_reliable = False
            for flow in flows:
                if not isinstance(flow, dict) or not _safe_text(flow.get("name")):
                    continue
                flow_name = _safe_text(flow.get("name"))
                flow_status = _status_from(flow, "unknown")
                flow_metadata = {"server": server_name, "application": app_name}
                flow_active = flow.get("active") if isinstance(flow.get("active"), dict) else {}
                flow_properties = flow.get("properties") if isinstance(flow.get("properties"), dict) else {}
                _copy_metadata(flow_metadata, flow_active, (
                    ("threads", "threads"),
                    ("threadsInUse", "threads_in_use"),
                    ("threadsDemanded", "threads_demanded"),
                    ("threadsCapacity", "threads_capacity"),
                    ("resourceState", "resource_state"),
                    ("monitoring", "monitoring"),
                    ("monitoringProfile", "monitoring_profile"),
                    ("openTelemetryEnabled", "open_telemetry_enabled"),
                ))
                _copy_metadata(flow_metadata, flow_properties, (
                    ("startMode", "start_mode"),
                    ("additionalInstances", "additional_instances"),
                    ("maximumRateMsgsPerSec", "maximum_rate_msgs_per_sec"),
                    ("notificationThresholdMsgsPerSec", "notification_threshold_msgs_per_sec"),
                    ("processingTimeoutSec", "processing_timeout_sec"),
                    ("processingTimeoutAction", "processing_timeout_action"),
                    ("commitCount", "commit_count"),
                    ("commitInterval", "commit_interval"),
                    ("coordinatedTransaction", "coordinated_transaction"),
                    ("wlmPolicy", "wlm_policy"),
                    ("monitoringProfile", "monitoring_profile"),
                    ("openTelemetryEnabled", "open_telemetry_enabled"),
                ))
                flow_resources.append(_resource(
                    "ace_message_flow",
                    server_name + "/" + app_name + "/" + flow_name,
                    flow_name,
                    flow_status,
                    flow_metadata,
                    [common.metric_string("flow_status", flow_status)],
                    server_name,
                ))

        server_metrics = [common.metric_string("server_status", server_status)]
        if flow_counts_reliable:
            server_metrics.append(common.metric_number("deployed_flow_count", len(flow_resources)))
            server_metrics.append(common.metric_number(
                "active_flow_count",
                sum(1 for flow in flow_resources if _is_active_flow_status(flow.get("status"))),
            ))
        resources.append(_resource(
            "ace_integration_server",
            server_name,
            server_name,
            server_status,
            metadata,
            [metric for metric in server_metrics if metric],
        ))
        resources.extend(flow_resources)

    if not resources:
        classes.Err("ibmace optadvisor REST discovered no integration servers; falling back to Java Integration API")
        return None

    return {"target": target, "resources": resources}


def _rest_statistics_subtype(subtype):
    text = _safe_text(subtype) or "apiv2"
    if text.startswith("/"):
        text = text.strip("/") or "apiv2"
    normalized = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in text)
    return normalized[:80] or "apiv2"


def _ace_rest_path(subtype, values):
    text = _safe_text(subtype)
    lower = text.lower()
    if text.startswith("/"):
        return text
    if lower in ("node", "integration_node", "integrationnode", "apiv2"):
        return "/apiv2?depth=2"
    if lower in ("jvm", "odbc", "servers", "integration_servers", "integrationservers"):
        return "/apiv2/servers?depth=3"
    server_name = _safe_text(values.get("server") or values.get("integration_server"))
    if lower in ("applications", "messageflows", "flows") and server_name:
        return "/apiv2/servers/" + quote(server_name, safe="") + "?depth=3"
    return "/apiv2?depth=2"


def _collect_rest_statistics(thisnode, values, metrics):
    base_url = _rest_base_url(thisnode, {}, values)
    verify = _rest_verify({}, values)
    auth = (values.get("usr", ""), _rest_password(values))
    cache = {}

    for subtype, logdir in metrics.items():
        path = _ace_rest_path(subtype, values)
        try:
            if path not in cache:
                cache[path] = _rest_get(base_url, path, auth, verify)
            common.write_numeric_tree(
                logdir,
                _rest_statistics_subtype(subtype),
                thisnode,
                cache[path],
            )
        except Exception as err:
            classes.Err("ibmace rest statistics error:" + str(err))


def restAvailabilityCheck(thisnode, values):
    base_url = _rest_base_url(thisnode, {}, values)
    verify = _rest_verify({}, values)
    auth = (values.get("usr", ""), _rest_password(values))
    payload = _rest_get(base_url, "/apiv2?depth=2", auth, verify)
    if not isinstance(payload, dict):
        return 0
    if _safe_text(payload.get("type")).lower() == "integrationnode" and _safe_text(payload.get("name")):
        return 1
    active = payload.get("active") if isinstance(payload.get("active"), dict) else {}
    if active.get("processId"):
        return 1
    descriptive = payload.get("descriptiveProperties") if isinstance(payload.get("descriptiveProperties"), dict) else {}
    if descriptive.get("version") or descriptive.get("productName"):
        return 1
    return 0


def _generic_stat_mapping():
    return {
        "noteq": "key",
        "node": 1,
        "server": 1,
        "keys": {
            "timestamp": 2,
            "count": 3,
        },
    }


def _post_rest_statistics(website, webssl, stat_data):
    if not isinstance(stat_data, dict):
        return
    mapping = _generic_stat_mapping()
    for subtype, logdir in stat_data.items():
        file_path = os.path.join(str(logdir), "Statistics_" + _rest_statistics_subtype(subtype) + ".csv")
        ret = file_utils.csv_json(file_path, mapping, "", True)
        try:
            retarr = json.loads(ret)
        except (json.JSONDecodeError, TypeError, ValueError):
            retarr = {}
        if not retarr:
            continue
        makerequest.postStatData(
            webssl,
            website,
            json.dumps(
                {
                    "type": "ibmace",
                    "subtype": _rest_statistics_subtype(subtype),
                    "data": retarr,
                }
            ),
        )


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
        classes.Err("ibmace optadvisor collector error:" + _java_result_error(java_result))
        return None

    appcode = _safe_text(config.get("appcode"))
    server_id = _safe_text(_get_server_id(config, thisnode))
    if not server_id:
        classes.Err("ibmace optadvisor disabled for missing server_id")
        return None

    resources = java_result.get("resources", [])
    if not isinstance(resources, list) or len(resources) == 0:
        classes.Err("ibmace optadvisor skipped no resources")
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
            "execution_id": "ibmace-" + node_id + "-" + uuid.uuid4().hex[:22],
            "type": "local",
            "execution_host": socket.gethostname(),
        },
        "target": java_result.get("target", {}),
        "resources": resources,
    }


def _java_arg(thisnode, config, values):
    server = values.get("integration_server") or config.get("integration_server") or ""
    if not server:
        candidate = values.get("server") or config.get("server") or ""
        if _safe_text(candidate).lower() != _safe_text(thisnode).lower():
            server = candidate
    payload = {
        "type": "OPTADVISOR",
        "host": values.get("host") or config.get("host") or thisnode,
        "port": int(values.get("port") or config.get("port") or 4414),
        "server": server,
        "usr": values.get("usr", ""),
        "pwd": values.get("pwd", ""),
        "ssl": values.get("ssl") or config.get("ssl") or "no",
    }
    return json.dumps(payload)


def _java_classpath(jar_path):
    return "/midleolibs/vendor/IntegrationAPI_ACE.jar:/midleolibs/libs/*:" + jar_path


def _java_env():
    env = os.environ.copy()
    env["LANG"] = "C"
    env["LC_ALL"] = "C"
    return env


def _collect_optadvisor(thisnode, config, values, jar_path):
    rest_result = _rest_collect_optadvisor(thisnode, config, values)
    if rest_result is not None:
        payload = buildOptAdvisorPayload(thisnode, config, rest_result, _utc_now())
        if payload is not None:
            _append_optadvisor_payload(thisnode, payload)
            return

    command = [
        "java",
        "-cp",
        _java_classpath(jar_path),
        "midleoace.midleo_ace_main",
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
        classes.Err("ibmace optadvisor timed out after " + str(common.DEFAULT_TIMEOUT_SECONDS) + " seconds")
        return
    except OSError as err:
        classes.Err("ibmace optadvisor failed to start:" + str(err))
        return

    if result.stderr:
        classes.Err("ibmace optadvisor Error:" + result.stderr[-common.MAX_LOG_BYTES:])
    if result.returncode != 0:
        classes.Err("ibmace optadvisor failed with exit code " + str(result.returncode))
        return

    try:
        payload_line = _java_payload_line(result.stdout)
        if not payload_line:
            classes.Err("ibmace optadvisor returned no JSON payload")
            return
        java_result = json.loads(payload_line)
        payload = buildOptAdvisorPayload(thisnode, config, java_result, _utc_now())
        if payload is not None:
            _append_optadvisor_payload(thisnode, payload)
    except (json.JSONDecodeError, TypeError, ValueError) as err:
        classes.Err("ibmace optadvisor payload parse error:" + str(err))


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
                "integration_server": "",
                "ssl": "no",
                "sslenabled": "",
                "docker": "",
                "contname": "",
                "sslverify": "",
                "ssl_verify": "",
                "conntype": "jms",
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
        if metrics and common.connection_type(values) == "rest":
            _collect_rest_statistics(thisqm, values, metrics)
        if common.optadvisor_collection_enabled(optadvisor_config):
            jar_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "resources",
                "midleoace.jar",
            )
            _collect_optadvisor(thisqm, optadvisor_config, values, jar_path)

    except (json.JSONDecodeError, TypeError, ValueError) as err:
        classes.Err("Error in ibmace statistics:" + str(err))


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
                if res is None or res.status_code < 200 or res.status_code >= 300:
                    remaining.append(line)
            except (json.JSONDecodeError, TypeError, ValueError) as err:
                classes.Err("ibmace optadvisor payload parse error:" + str(err))
            except Exception as err:
                classes.Err("ibmace optadvisor post error:" + str(err))
                remaining.append(line)

        with open(file, "w", encoding="utf-8") as f:
            f.writelines(remaining)
    except OSError as err:
        classes.Err("ibmace optadvisor file error:" + str(err))


def resetStat(thisnode, website, webssl, _legacy_token, stat_data):
    optadvisor_config, legacy_stat_data = _split_optadvisor_config(stat_data if isinstance(stat_data, dict) else {})
    _, legacy_stat_data = common.pop_fields(
        legacy_stat_data,
        {
            "usr": "",
            "pwd": "",
            "srvuser": "",
            "srvpass": "",
            "host": "",
            "port": "",
            "mngmport": "",
            "jmxport": "",
            "webport": "",
            "server": "",
            "integration_server": "",
            "ssl": "",
            "sslenabled": "",
            "conntype": "",
            "docker": "",
            "contname": "",
            "sslverify": "",
            "ssl_verify": "",
        },
    )
    if common.optadvisor_collection_enabled(optadvisor_config):
        _queue_optadvisor_jvm_stats(thisnode, optadvisor_config, legacy_stat_data)
    _post_rest_statistics(website, webssl, legacy_stat_data)
    common.post_csv_stats(
        "ibmace",
        lambda subtype: "ibmace" + subtype,
        website,
        webssl,
        _legacy_token,
        legacy_stat_data,
        lambda logdir, subtype: logdir + "ResourceStats_" + thisnode + "_*_" + subtype + ".txt",
    )
    flushOptAdvisorTelemetry(thisnode, website, webssl, _legacy_token, stat_data)
