import json
import os
import socket
import urllib.parse
import uuid
from datetime import datetime, timezone

from modules.base import classes, makerequest
from modules.statistics import common


OPTADVISOR_SCHEMA_VERSION = "1.0"
OPTADVISOR_COLLECTOR_NAME = "weblogic-rest-collector"
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


def _normalize_target(thisnode, collect_result, resources):
    target = collect_result.get("target", {})
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


def buildOptAdvisorPayload(thisnode, config, collect_result, collected_at=None):
    if not _optadvisor_enabled(config):
        return None
    if not isinstance(collect_result, dict):
        classes.Err("weblogic optadvisor returned invalid collector result")
        return None
    if collect_result.get("error") == "yes":
        errorlog = collect_result.get("errorlog") or collect_result.get("log") or collect_result.get("err") or "unknown collector error"
        classes.Err("weblogic optadvisor collector error:" + str(errorlog)[-common.MAX_LOG_BYTES:])
        return None

    server_id = _safe_text(_get_server_id(config, thisnode))
    if not server_id:
        classes.Err("weblogic optadvisor disabled for missing server_id")
        return None

    resources = collect_result.get("resources", [])
    if not isinstance(resources, list) or len(resources) == 0:
        classes.Err("weblogic optadvisor returned no resources")
        return None

    target = _normalize_target(thisnode, collect_result, resources)
    resources = _normalize_resources(resources, target)
    node_id = "".join(ch if ch.isalnum() or ch in ("_", "-", ".") else "-" for ch in str(thisnode))[:24]
    payload = {
        "schema_version": OPTADVISOR_SCHEMA_VERSION,
        "collected_at": _iso_utc(collected_at),
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
    return payload


def _resource_key(appserver, name):
    appserver = _safe_text(appserver)
    name = _safe_text(name)
    return appserver + "/" + name if appserver and name else name or appserver


def _resource(resource_type, key, name, status, metrics, metadata=None):
    item = {
        "resource_type": resource_type,
        "technical_key": key,
        "name": name,
        "status": _normalize_status(status),
        "metadata": metadata if isinstance(metadata, dict) else {},
        "metrics": [metric for metric in metrics if isinstance(metric, dict)],
    }
    return item if item["metrics"] else None


def _add_number_metric(metrics, key, value):
    common.add_metric(metrics, common.metric_number(key, value))


def _add_string_metric(metrics, key, value):
    common.add_metric(metrics, common.metric_string(key, value))


def _payload_items(payload):
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return _weblogic_rest_items(payload)


def _rest_item_name(item):
    return _safe_text(_case_value(item, ("name", "Name", "serverName", "ServerName")))


def _rest_first(base_url, values, paths, label):
    for path in paths:
        try:
            payload = common.rest_json_request(base_url, path, values)
            if payload:
                return payload
        except Exception as err:
            classes.Err("weblogic optadvisor REST " + label + " failed path:" + path + " error:" + str(err))
    return {}


def _server_runtime_paths(appserver):
    encoded_server = urllib.parse.quote(_safe_text(appserver), safe="")
    paths = []
    if encoded_server:
        paths.append("/management/weblogic/latest/domainRuntime/serverRuntimes/" + encoded_server)
    paths.append("/management/weblogic/latest/serverRuntime")
    paths.append("/management/weblogic/latest/domainRuntime/serverRuntimes")
    return paths


def _select_named_payload(payload, wanted_name):
    wanted = _safe_text(wanted_name).lower()
    if not wanted:
        return payload if isinstance(payload, dict) else {}
    if isinstance(payload, dict) and _rest_item_name(payload).lower() == wanted:
        return payload
    for item in _payload_items(payload):
        if _rest_item_name(item).lower() == wanted:
            return item
    return payload if isinstance(payload, dict) and not _payload_items(payload) else {}


def _local_and_domain_paths(appserver, suffix):
    encoded_server = urllib.parse.quote(_safe_text(appserver), safe="")
    paths = []
    if encoded_server:
        paths.append("/management/weblogic/latest/domainRuntime/serverRuntimes/" + encoded_server + suffix)
    paths.append("/management/weblogic/latest/serverRuntime" + suffix)
    return paths


def _is_internal_application(item):
    name = _safe_text(_case_value(item, ("applicationName", "ApplicationName", "name", "Name"))).lower()
    internal = _case_value(item, ("internal", "Internal"))
    if common.truthy(internal):
        return True
    return (
        not name
        or name.startswith("wls-")
        or name.startswith("bea_")
        or name == "weblogic"
        or name == "consoleapp"
        or name.startswith("consolehelp")
        or name.startswith("bea_wls_internal")
        or name.startswith("jms-internal")
    )


def _deployment_counts(base_url, values, appserver):
    payload = _rest_first(
        base_url,
        values,
        _local_and_domain_paths(appserver, "/applicationRuntimes"),
        "applicationRuntimes",
    )
    deployed = 0
    active = 0
    for item in _payload_items(payload):
        if _is_internal_application(item):
            continue
        deployed += 1
        runtime_state = _safe_text(_case_value(item, ("state", "State", "runtimeState"))).lower()
        version_state = common.numeric_value(_case_value(item, ("activeVersionState", "ActiveVersionState")))
        if (
            "active" in runtime_state
            or "running" in runtime_state
            or "prepared" in runtime_state
            or (version_state is not None and int(version_state) == 2)
        ):
            active += 1
    return deployed, active


def _server_resource(base_url, values, appserver, target):
    server_name = _safe_text(target.get("server_name")) or _safe_text(appserver) or "weblogic-server"
    status = _normalize_status(target.get("status"))
    metrics = []
    _add_string_metric(metrics, "server_status", status)
    deployed, active = _deployment_counts(base_url, values, server_name)
    _add_number_metric(metrics, "deployment_count", deployed)
    _add_number_metric(metrics, "active_deployment_count", active)
    return _resource("weblogic_server", _resource_key(server_name, "server"), server_name, status, metrics)


def _collect_jvm_resource(base_url, values, appserver):
    payload = _rest_first(
        base_url,
        values,
        _local_and_domain_paths(appserver, "/JVMRuntime"),
        "JVMRuntime",
    )
    if not isinstance(payload, dict):
        return None
    name = _rest_item_name(payload) or (_safe_text(appserver) + "/JVMRuntime")
    heap_size = common.numeric_value(_case_value(payload, ("heapSizeCurrent", "HeapSizeCurrent")))
    heap_free = common.numeric_value(_case_value(payload, ("heapFreeCurrent", "HeapFreeCurrent")))
    heap_free_percent = common.numeric_value(_case_value(payload, ("heapFreePercent", "HeapFreePercent")))
    metrics = []
    if heap_size is not None and heap_free is not None:
        _add_number_metric(metrics, "heap_used_bytes", max(0.0, heap_size - heap_free))
    if heap_free_percent is not None:
        _add_number_metric(metrics, "heap_free_percent", heap_free_percent)
        _add_number_metric(metrics, "heap_used_percent", 100.0 - heap_free_percent)
    elif heap_size is not None and heap_size > 0 and heap_free is not None:
        used_percent = ((heap_size - heap_free) / heap_size) * 100.0
        _add_number_metric(metrics, "heap_used_percent", used_percent)
        _add_number_metric(metrics, "heap_free_percent", 100.0 - used_percent)
    return _resource("weblogic_jvm", _resource_key(appserver, name), name, "running", metrics)


def _collect_thread_pool_resource(base_url, values, appserver):
    payload = _rest_first(
        base_url,
        values,
        _local_and_domain_paths(appserver, "/threadPoolRuntime"),
        "threadPoolRuntime",
    )
    if not isinstance(payload, dict):
        return None
    name = _rest_item_name(payload) or "ThreadPoolRuntime"
    total = common.numeric_value(_case_value(payload, ("executeThreadTotalCount", "ExecuteThreadTotalCount")))
    idle = common.numeric_value(_case_value(payload, ("executeThreadIdleCount", "ExecuteThreadIdleCount")))
    metrics = []
    _add_number_metric(metrics, "stuck_thread_count", _case_value(payload, ("stuckThreadCount", "StuckThreadCount")))
    _add_number_metric(metrics, "hogging_thread_count", _case_value(payload, ("hoggingThreadCount", "HoggingThreadCount")))
    _add_number_metric(metrics, "execute_thread_total_count", total)
    _add_number_metric(metrics, "execute_thread_idle_count", idle)
    if total is not None and idle is not None and total > 0 and idle <= total:
        _add_number_metric(metrics, "execute_thread_busy_percent", max(0.0, total - idle) * 100.0 / total)
    return _resource("weblogic_thread_pool", _resource_key(appserver, name), name, "running", metrics)


def _collect_jdbc_resources(base_url, values, appserver):
    payload = _rest_first(
        base_url,
        values,
        _local_and_domain_paths(appserver, "/JDBCServiceRuntime/JDBCDataSourceRuntimeMBeans"),
        "JDBCDataSourceRuntimeMBeans",
    )
    resources = []
    for item in _payload_items(payload):
        name = _rest_item_name(item) or "JDBCDataSourceRuntime"
        state = _safe_text(_case_value(item, ("state", "State"))) or "unknown"
        active = common.numeric_value(_case_value(item, ("activeConnectionsCurrentCount", "ActiveConnectionsCurrentCount")))
        capacity = common.numeric_value(_case_value(item, ("currCapacity", "CurrCapacity")))
        metrics = []
        _add_number_metric(metrics, "active_connections_current_count", active)
        _add_number_metric(metrics, "curr_capacity", capacity)
        if active is not None and capacity is not None and capacity > 0:
            _add_number_metric(metrics, "connection_usage_percent", active * 100.0 / capacity)
        _add_number_metric(metrics, "waiting_for_connection_current_count", _case_value(item, ("waitingForConnectionCurrentCount", "WaitingForConnectionCurrentCount")))
        _add_number_metric(metrics, "leaked_connection_count", _case_value(item, ("leakedConnectionCount", "LeakedConnectionCount")))
        resource = _resource("weblogic_jdbc_datasource", _resource_key(appserver, name), name, state, metrics)
        if resource:
            resources.append(resource)
    return resources


def _collect_jms_resources(base_url, values, appserver):
    server_payload = _rest_first(
        base_url,
        values,
        _local_and_domain_paths(appserver, "/JMSRuntime/JMSServers"),
        "JMSServers",
    )
    resources = []
    for jms_server in _payload_items(server_payload):
        jms_name = _rest_item_name(jms_server)
        destinations = []
        for key in ("destinations", "Destinations", "JMSDestinationRuntimes", "jmsDestinationRuntimes"):
            value = jms_server.get(key)
            if value:
                destinations = _payload_items(value) or ([value] if isinstance(value, dict) else [])
                break
        if not destinations and jms_name:
            destination_payload = _rest_first(
                base_url,
                values,
                _local_and_domain_paths(
                    appserver,
                    "/JMSRuntime/JMSServers/" + urllib.parse.quote(jms_name, safe="") + "/destinations",
                ),
                "JMS destinations",
            )
            destinations = _payload_items(destination_payload)
        for destination in destinations:
            name = _rest_item_name(destination) or "JMSDestinationRuntime"
            metrics = []
            _add_number_metric(metrics, "messages_current_count", _case_value(destination, ("messagesCurrentCount", "MessagesCurrentCount")))
            _add_number_metric(metrics, "messages_pending_count", _case_value(destination, ("messagesPendingCount", "MessagesPendingCount")))
            _add_number_metric(metrics, "consumers_current_count", _case_value(destination, ("consumersCurrentCount", "ConsumersCurrentCount")))
            resource = _resource("weblogic_jms_destination", _resource_key(appserver, name), name, "running", metrics)
            if resource:
                resources.append(resource)
    return resources


def _rest_collect_optadvisor(thisnode, config, values):
    base_url, _ = common.rest_base_url(thisnode, values, values.get("mngmport") or "7001")
    appserver = _safe_text(_get_appserver(config, thisnode))
    root = _rest_first(base_url, values, _server_runtime_paths(appserver), "serverRuntime")
    server_payload = _select_named_payload(root, appserver)
    server_name = _rest_item_name(server_payload) or appserver or thisnode
    status = _normalize_status(_case_value(server_payload, ("state", "State", "serverState")))
    metadata = {}
    cluster = _case_value(server_payload, ("cluster", "Cluster", "clusterName", "ClusterName"))
    if cluster:
        metadata["cluster_name"] = _safe_text(cluster)
    target = {
        "status": status,
        "server_name": server_name,
        "metadata": metadata,
    }
    resources = []
    server_resource = _server_resource(base_url, values, server_name, target)
    if server_resource:
        resources.append(server_resource)
    for resource in (
        _collect_jvm_resource(base_url, values, server_name),
        _collect_thread_pool_resource(base_url, values, server_name),
    ):
        if resource:
            resources.append(resource)
    resources.extend(_collect_jdbc_resources(base_url, values, server_name))
    resources.extend(_collect_jms_resources(base_url, values, server_name))
    return {"target": target, "resources": resources}


def _collect_optadvisor(thisnode, config, values):
    classes.Err("weblogic optadvisor REST start:" + str(thisnode))
    try:
        collect_result = _rest_collect_optadvisor(thisnode, config, values)
        payload = buildOptAdvisorPayload(thisnode, config, collect_result, _utc_now())
        if payload is not None:
            _append_optadvisor_payload(thisnode, payload)
    except Exception as err:
        classes.Err("weblogic optadvisor REST error:" + str(err))


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
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
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
                "sslverify": "",
                "ssl_verify": "",
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
            _collect_optadvisor(thisqm, optadvisor_config, values)

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
