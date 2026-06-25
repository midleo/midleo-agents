import csv
import glob
import json
import os
import socket
import sys
import uuid
from urllib.parse import quote
from datetime import datetime, timezone

import requests
import urllib3

from modules.base import decrypt, file_utils
from modules.base import classes, makerequest, statarr
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
ACE_STATS_DEPTH = "5"
ACE_FLOW_STATS_CSV_MARKERS = (
    "TotalInputMessages",
    "TotalNumberOfInputMessages",
    "MessageFlowName",
)
APPLSTAT_SKIP_KEYS = OPTADVISOR_CONFIG_KEYS | {
    "usr",
    "pwd",
    "srvuser",
    "srvpass",
    "host",
    "port",
    "mngmport",
    "jmxport",
    "webport",
    "server",
    "integration_server",
    "ssl",
    "sslenabled",
    "conntype",
    "docker",
    "contname",
    "sslverify",
    "ssl_verify",
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


def _raise_csv_field_limit():
    max_size = sys.maxsize
    while True:
        try:
            csv.field_size_limit(max_size)
            return
        except OverflowError:
            max_size = int(max_size / 10)


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


def _normalize_logdir(logdir):
    text = _safe_text(logdir)
    if not text:
        return ""
    return text if text.endswith(("/", "\\")) else text + "/"


def _resource_stats_pattern(logdir, thisnode, subtype):
    return _normalize_logdir(logdir) + "ResourceStats_" + str(thisnode) + "_*_" + str(subtype) + ".txt"


def _get_applstat_metrics(thisnode, stat_data=None):
    metrics = {}
    sources = []
    if isinstance(stat_data, dict):
        sources.append(stat_data)
    try:
        from modules.base import configs

        node_cfg = configs.getmonData().get(OPTADVISOR_TECHNOLOGY, {}).get(str(thisnode), {})
        if isinstance(node_cfg, dict):
            sources.append(node_cfg)
    except Exception:
        pass
    for source in sources:
        for key, value in source.items():
            key_text = _safe_text(key)
            if not key_text or key_text in APPLSTAT_SKIP_KEYS or str(key).startswith("optadvisor_"):
                continue
            if isinstance(value, str) and value.strip():
                metrics[key_text] = value.strip()
    return metrics


def _applstat_stats_file_paths(thisnode, stat_metrics=None):
    metrics = stat_metrics if isinstance(stat_metrics, dict) and stat_metrics else _get_applstat_metrics(thisnode)
    paths = []
    logdirs = set()
    for subtype, logdir in metrics.items():
        normalized = _normalize_logdir(logdir)
        if not normalized:
            continue
        logdirs.add(normalized)
        paths.extend(glob.glob(_resource_stats_pattern(normalized, thisnode, subtype)))
    for logdir in logdirs:
        paths.extend(glob.glob(logdir + "*flowStats*.csv"))
        paths.extend(glob.glob(logdir + "*SnapShot*.csv"))
    deduped = []
    seen = set()
    for path in paths:
        normalized = os.path.normpath(path)
        if normalized not in seen and os.path.isfile(normalized):
            seen.add(normalized)
            deduped.append(normalized)
    return deduped


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


RESOURCE_STATS_CPU_HEADERS = (
    "PercentCPU",
    "ProcessCpuUtilization",
    "CpuUtilization",
)


def _statarr_for_resource_subtype(subtype):
    if str(subtype or "").lower() == "odbc":
        return statarr.ibmaceODBC()
    return statarr.ibmaceJVM()


def _resource_stats_subtype_from_path(file_path):
    base = os.path.basename(str(file_path))
    lower = base.lower()
    if not lower.startswith("resourcestats_") or not lower.endswith(".txt"):
        return "jvm"
    stem = base[:-4]
    subtype = stem.rsplit("_", 1)[-1]
    return subtype or "jvm"


def _memory_used_bytes_from_used_value(used_value):
    number = _number(used_value)
    if number is None:
        return None
    if number < 100000:
        return number * 1024 * 1024
    return number


def _resource_stats_min_row_len(stat_def):
    indices = [stat_def.get("node", 0), stat_def.get("server", 0)]
    indices.extend(stat_def.get("keys", {}).values())
    return max(indices) + 1


def _queue_optadvisor_jvm_stats(thisnode, config, legacy_stat_data):
    if not isinstance(legacy_stat_data, dict):
        return
    resources = {}
    target_node = str(thisnode)
    stat_def = statarr.ibmaceJVM()
    server_col = stat_def.get("server", 2)
    used_col = stat_def.get("keys", {}).get("used", 7)
    max_col = stat_def.get("keys", {}).get("max", 9)
    min_len = _resource_stats_min_row_len(stat_def)

    for subtype, logdir in legacy_stat_data.items():
        if str(subtype).lower() != "jvm":
            continue
        pattern = _resource_stats_pattern(logdir, thisnode, subtype)
        for file_path in glob.glob(pattern):
            try:
                _raise_csv_field_limit()
                with open(file_path, "r", encoding="utf-8", errors="ignore", newline="") as f:
                    for row in csv.reader((line.replace("\0", "") for line in f), delimiter=","):
                        if len(row) < min_len or row[0] == "ResourceName":
                            continue
                        node_name = _safe_text(row[stat_def.get("node", 1)])
                        server_name = _safe_text(row[server_col])
                        used_value = _memory_used_bytes_from_used_value(
                            row[used_col] if len(row) > used_col else None
                        )
                        max_value = _number(row[max_col] if len(row) > max_col else None)
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
                            max_bytes = _memory_used_bytes_from_used_value(max_value)
                            resource["metadata"]["jvmMaxHeapSize"] = (
                                max_bytes if max_bytes is not None else max_value
                            )
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


def _rest_verify(config, values):
    for source in (values or {}, config or {}):
        for key in ("ssl_verify", "sslverify"):
            value = source.get(key)
            if value is not None and str(value).strip() != "":
                return common.truthy(value)
    return False


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
        if isinstance(data, dict):
            return data
        if isinstance(data, list):
            return {"children": [item for item in data if isinstance(item, dict)]}
        return {}
    except requests.exceptions.RequestException as err:
        classes.Err("ibmace optadvisor REST error:" + str(err))
    except (json.JSONDecodeError, TypeError, ValueError) as err:
        classes.Err("ibmace optadvisor REST parse error:" + str(err))
    return {}


def _rest_get_statistics(base_url, path, auth, verify, context=""):
    payload = _rest_get(base_url, path, auth, verify)
    if not payload:
        if context:
            classes.Err("ibmace optadvisor stats fetch failed:" + context + " path:" + path)
        return {}
    return payload


def _statistics_payload_has_counters(properties):
    if not isinstance(properties, dict):
        return False
    counter_keys = (
        "TotalInputMessages",
        "TotalNumberOfInputMessages",
        "totalInputMessages",
        "TotalNumberOfMessagesWithErrors",
        "UsedMemoryInMB",
        "ProcessCpuUtilization",
        "PercentCPU",
    )
    return any(key in properties and properties[key] not in (None, "") for key in counter_keys)


def _statistics_publication_active(payload):
    if not isinstance(payload, dict):
        return False
    for section_key in ("active", "properties"):
        section = payload.get(section_key)
        if not isinstance(section, dict):
            continue
        for flag_key in ("publicationOn", "reportingOn", "archivalOn"):
            flag = _safe_text(section.get(flag_key)).lower()
            if flag in ("active", "on", "enabled", "true", "yes"):
                return True
    return False


def _first_present_ci(data, *keys):
    if not isinstance(data, dict):
        return None
    lowered = {}
    for key, value in data.items():
        text_key = _safe_text(key).lower()
        if text_key and text_key not in lowered:
            lowered[text_key] = value
    for key in keys:
        value = lowered.get(_safe_text(key).lower())
        if value not in (None, ""):
            return value
    return None


def _iter_json_dict_nodes(payload):
    if not isinstance(payload, dict):
        return
    stack = [payload]
    while stack:
        current = stack.pop()
        if not isinstance(current, dict):
            continue
        yield current
        for value in current.values():
            if isinstance(value, dict):
                stack.append(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        stack.append(item)


def _flow_app_key(app_name):
    app = _safe_text(app_name)
    if not app or app.lower() == "_standalone":
        return "_default"
    return app


def _flow_resource_key(server_name, app_name, flow_name):
    server = _safe_text(server_name)
    flow = _safe_text(flow_name)
    if not server or not flow:
        return ""
    return (server + "/" + _flow_app_key(app_name) + "/" + flow).lower()


def _flow_server_name_key(server_name, flow_name):
    server = _safe_text(server_name)
    flow = _safe_text(flow_name)
    if not server or not flow:
        return ""
    return (server + "/" + flow).lower()


def _flow_record_identity(record):
    if not isinstance(record, dict):
        return None, None, None
    message_flow = record.get("MessageFlow")
    if isinstance(message_flow, dict):
        merged = dict(record)
        merged.update(message_flow)
        record = merged
    server_name = _safe_text(_first_present_ci(
        record,
        "ExecutionGroupName",
        "executionGroupName",
        "integrationServerName",
        "server",
    ))
    app_name = _flow_app_key(_first_present_ci(
        record,
        "ApplicationName",
        "applicationName",
        "application",
    ))
    flow_name = _safe_text(_first_present_ci(
        record,
        "MessageFlowName",
        "messageFlowName",
        "name",
    ))
    if server_name and flow_name:
        return server_name, app_name, flow_name
    return None, None, None


def _iter_flow_statistics_records(payload):
    seen = set()
    for node in _iter_json_dict_nodes(payload):
        candidates = []
        accounting = node.get("WMQIStatisticsAccounting")
        if isinstance(accounting, dict):
            for value in accounting.values():
                if isinstance(value, dict):
                    candidates.append(value)
        if _first_present_ci(node, "TotalInputMessages", "TotalNumberOfInputMessages") is not None:
            candidates.append(node)
        for candidate in candidates:
            server_name, app_name, flow_name = _flow_record_identity(candidate)
            if not server_name or not flow_name:
                continue
            identity = _flow_resource_key(server_name, app_name, flow_name)
            if identity in seen:
                continue
            seen.add(identity)
            yield server_name, app_name, flow_name, candidate


def _iter_server_resource_records(payload):
    seen = set()
    for node in _iter_json_dict_nodes(payload):
        blocks = []
        resource_statistics = node.get("ResourceStatistics")
        if isinstance(resource_statistics, dict):
            blocks.append(resource_statistics)
        if _first_present_ci(node, "UsedMemoryInMB", "ProcessCpuUtilization", "PercentCPU") is not None:
            blocks.append(node)
        for block in blocks:
            server_name = _safe_text(_first_present_ci(
                block,
                "executionGroupName",
                "ExecutionGroupName",
                "integrationServerName",
                "server",
            ))
            if not server_name:
                continue
            identity = server_name.lower()
            if identity in seen:
                continue
            seen.add(identity)
            properties = dict(block)
            resource_types = block.get("ResourceType")
            if isinstance(resource_types, list):
                for resource_type in resource_types:
                    if not isinstance(resource_type, dict):
                        continue
                    identifiers = resource_type.get("resourceIdentifier")
                    if not isinstance(identifiers, list):
                        continue
                    for identifier in identifiers:
                        if isinstance(identifier, dict):
                            properties.update(identifier)
            yield server_name, properties


def _normalize_csv_header(header):
    return _safe_text(header).replace("\ufeff", "")


def _csv_row_to_properties(headers, row):
    properties = {}
    for index, header in enumerate(headers):
        if index >= len(row):
            continue
        key = _normalize_csv_header(header)
        if not key or key == "ResourceName":
            continue
        value = row[index]
        if value not in (None, ""):
            properties[key] = value
    return properties


def _parse_flow_stats_csv_text(contents):
    rows = []
    if not contents:
        return rows
    try:
        _raise_csv_field_limit()
        reader = csv.reader(contents.splitlines())
        headers = None
        for row in reader:
            if not row:
                continue
            if headers is None:
                headers = [_normalize_csv_header(item) for item in row]
                if not any(marker in headers for marker in ACE_FLOW_STATS_CSV_MARKERS):
                    headers = None
                continue
            properties = _csv_row_to_properties(headers, row)
            server_name, app_name, flow_name = _flow_record_identity(properties)
            if server_name and flow_name:
                rows.append((server_name, app_name, flow_name, properties))
    except (csv.Error, TypeError, ValueError) as err:
        classes.Err("ibmace optadvisor stats csv parse error:" + str(err))
    return rows


def _parse_resource_stats_text(contents, subtype="jvm"):
    rows = []
    if not contents:
        return rows
    stat_def = _statarr_for_resource_subtype(subtype)
    server_col = stat_def.get("server", 2)
    used_col = stat_def.get("keys", {}).get("used", 7)
    min_len = _resource_stats_min_row_len(stat_def)
    try:
        _raise_csv_field_limit()
        reader = csv.reader(contents.splitlines())
        headers = None
        for row in reader:
            if not row:
                continue
            if row[0] == "ResourceName":
                headers = [_normalize_csv_header(item) for item in row]
                continue
            if len(row) < min_len:
                continue
            server_name = _safe_text(row[server_col])
            if not server_name:
                continue
            properties = {}
            if headers:
                prop_map = _csv_row_to_properties(headers, row)
                if "UsedMemoryInMB" in prop_map:
                    properties["UsedMemoryInMB"] = prop_map["UsedMemoryInMB"]
                for cpu_header in RESOURCE_STATS_CPU_HEADERS:
                    if cpu_header in prop_map:
                        properties[cpu_header] = prop_map[cpu_header]
            if "UsedMemoryInMB" not in properties and len(row) > used_col:
                properties["UsedMemoryInMB"] = row[used_col]
            rows.append((server_name, properties))
    except (csv.Error, TypeError, ValueError) as err:
        classes.Err("ibmace optadvisor resource stats parse error:" + str(err))
    return rows


def _parse_flow_stats_csv_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore", newline="") as handle:
            return _parse_flow_stats_csv_text(handle.read())
    except OSError as err:
        classes.Err("ibmace optadvisor stats csv read error:" + str(err))
        return []


def _parse_resource_stats_file(file_path):
    subtype = _resource_stats_subtype_from_path(file_path)
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore", newline="") as handle:
            return _parse_resource_stats_text(handle.read(), subtype)
    except OSError as err:
        classes.Err("ibmace optadvisor resource stats read error:" + str(err))
        return []


def _apply_flow_stats_records(resources, records):
    if not records:
        return
    flow_index = {}
    flow_name_index = {}
    duplicate_flow_names = set()
    for resource in resources:
        if not isinstance(resource, dict) or resource.get("resource_type") != "ace_message_flow":
            continue
        technical_key = _safe_text(resource.get("technical_key"))
        if technical_key:
            flow_index[technical_key.lower()] = resource
            parts = technical_key.split("/", 2)
            if len(parts) == 3:
                flow_index[_flow_resource_key(parts[0], parts[1], parts[2])] = resource
                name_key = _flow_server_name_key(parts[0], parts[2])
                if name_key:
                    if name_key in flow_name_index and flow_name_index[name_key] is not resource:
                        duplicate_flow_names.add(name_key)
                    else:
                        flow_name_index[name_key] = resource
    for name_key in duplicate_flow_names:
        flow_name_index.pop(name_key, None)
    for server_name, app_name, flow_name, properties in records:
        flow_key = _flow_resource_key(server_name, app_name, flow_name)
        resource = flow_index.get(flow_key)
        if resource is None and _flow_app_key(app_name) == "_default":
            resource = flow_name_index.get(_flow_server_name_key(server_name, flow_name))
        if resource is not None:
            _merge_resource_metrics(resource, _flow_statistics_metrics(properties))


def _apply_server_stats_records(resources, records):
    if not records:
        return
    server_index = {}
    for resource in resources:
        if not isinstance(resource, dict) or resource.get("resource_type") != "ace_integration_server":
            continue
        technical_key = _safe_text(resource.get("technical_key") or resource.get("name")).lower()
        if technical_key:
            server_index[technical_key] = resource
    for server_name, properties in records:
        resource = server_index.get(server_name.lower())
        if resource is not None:
            _merge_resource_metrics(resource, _server_statistics_metrics(properties))


def _enrich_from_statistics_files(thisnode, config, values, resources, stat_metrics=None):
    flow_records = []
    server_records = []
    flow_file_paths = []
    for file_path in _applstat_stats_file_paths(thisnode, stat_metrics):
        lowered = file_path.lower()
        if "resourcestats" in lowered:
            server_records.extend(_parse_resource_stats_file(file_path))
        else:
            flow_file_paths.append(file_path)
            flow_records.extend(_parse_flow_stats_csv_file(file_path))
    _apply_flow_stats_records(resources, flow_records)
    _apply_server_stats_records(resources, server_records)
    has_flow_metrics = False
    for resource in resources:
        if not isinstance(resource, dict) or resource.get("resource_type") != "ace_message_flow":
            continue
        if _resource_has_metric(resource, "message_count") or _resource_has_metric(resource, "error_count"):
            has_flow_metrics = True
            break
    if not flow_file_paths and not has_flow_metrics:
        classes.Err("ibmace optadvisor no flow stats files in confapplstat paths")


def _apply_json_statistics_payload(resources, payload):
    _apply_flow_stats_records(resources, list(_iter_flow_statistics_records(payload)))
    _apply_server_stats_records(resources, list(_iter_server_resource_records(payload)))


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


def _resource_has_metric(resource, key):
    metrics = resource.get("metrics") if isinstance(resource, dict) else None
    if not isinstance(metrics, list):
        return False
    wanted = _safe_text(key)
    for metric in metrics:
        if isinstance(metric, dict) and _safe_text(metric.get("key")) == wanted:
            return True
    return False


def _collect_property_values(payload):
    values = {}
    if not isinstance(payload, dict):
        return values
    for key in ("properties", "active", "descriptiveProperties"):
        section = payload.get(key)
        if isinstance(section, dict):
            for prop_key, prop_value in section.items():
                if prop_key not in values and prop_value not in (None, ""):
                    values[prop_key] = prop_value
    children = payload.get("children")
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                values.update(_collect_property_values(child))
    elif isinstance(children, dict):
        for child in children.values():
            if isinstance(child, dict):
                values.update(_collect_property_values(child))
    return values


def _collect_statistics_values(payload):
    values = _collect_property_values(payload)
    if not isinstance(payload, dict):
        return values
    for child_key in ("statistics", "accounting", "snapshot"):
        for child in _children(payload, child_key):
            values.update(_collect_property_values(child))
    for child in _children(payload):
        if not isinstance(child, dict):
            continue
        child_type = _safe_text(child.get("type")).lower()
        if "statistic" in child_type or "accounting" in child_type or "snapshot" in child_type:
            values.update(_collect_property_values(child))
    return values


def _embedded_statistics_metrics(source_payload, resource_type):
    values = _collect_statistics_values(source_payload)
    if resource_type == "ace_message_flow":
        return _flow_statistics_metrics(values)
    if resource_type == "ace_integration_server":
        return _server_statistics_metrics(values)
    return []


def _merge_resource_metrics(resource, new_metrics):
    if not isinstance(resource, dict) or not isinstance(new_metrics, list) or not new_metrics:
        return
    existing = resource.get("metrics")
    if not isinstance(existing, list):
        existing = []
    seen = {_safe_text(metric.get("key")) for metric in existing if isinstance(metric, dict)}
    for metric in new_metrics:
        if not isinstance(metric, dict):
            continue
        key = _safe_text(metric.get("key"))
        if key and key not in seen:
            existing.append(metric)
            seen.add(key)
    resource["metrics"] = existing


def _flow_statistics_metrics(properties):
    if not isinstance(properties, dict):
        return []
    metrics = []
    message_count = common.first_present(
        properties,
        "TotalInputMessages",
        "TotalNumberOfInputMessages",
        "totalInputMessages",
        "totalNumberOfInputMessages",
    )
    error_count = common.first_present(
        properties,
        "TotalNumberOfMessagesWithErrors",
        "TotalNumberOfErrorsProcessingMessages",
        "TotalErrors",
        "totalNumberOfMessagesWithErrors",
        "totalNumberOfErrorsProcessingMessages",
    )
    elapsed_avg = common.first_present(
        properties,
        "AverageElapsedTime",
        "AverageElapsedTimeProcessingInputMessages",
        "averageElapsedTime",
        "averageElapsedTimeProcessingInputMessages",
    )
    common.add_metric(metrics, common.metric_number("message_count", message_count))
    common.add_metric(metrics, common.metric_number("error_count", error_count))
    if elapsed_avg is not None:
        elapsed_number = common.numeric_value(elapsed_avg)
        if elapsed_number is not None:
            common.add_metric(metrics, common.metric_number("elapsed_time_avg_ms", elapsed_number / 1000.0))
    return metrics


def _server_statistics_metrics(properties):
    if not isinstance(properties, dict):
        return []
    metrics = []
    memory_value = common.first_present(
        properties,
        "UsedMemoryInMB",
        "usedMemoryInMB",
        "HeapMemoryUsed",
        "heapMemoryUsed",
        "memoryUsed",
    )
    if memory_value is not None:
        memory_number = common.numeric_value(memory_value)
        if memory_number is not None:
            if memory_number < 100000:
                memory_number *= 1024 * 1024
            common.add_metric(metrics, common.metric_number("memory_used_bytes", memory_number))
    cpu_value = common.first_present(
        properties,
        "ProcessCpuUtilization",
        "processCpuUtilization",
        "PercentCPU",
        "CpuUtilization",
        "cpuUtilization",
    )
    common.add_metric(metrics, common.metric_number("cpu_percent", cpu_value))
    return metrics


def _flow_statistics_paths(server_name, app_name, flow_name):
    server = quote(server_name, safe="")
    app = quote(app_name, safe="")
    flow = quote(flow_name, safe="")
    base = "/apiv2/servers/" + server + "/applications/" + app + "/messageflows/" + flow
    depth = "?depth=" + ACE_STATS_DEPTH
    return (
        base + "/statistics/snapshot" + depth,
        base + "/statistics" + depth,
    )


def _server_statistics_paths(server_name):
    server = quote(server_name, safe="")
    depth = "?depth=" + ACE_STATS_DEPTH
    return (
        "/apiv2/servers/" + server + "/statistics/resource-stats" + depth,
        "/apiv2/servers/" + server + "/statistics/snapshot" + depth,
        "/apiv2/servers/" + server + "/statistics" + depth,
    )


def _snapshot_statistics_paths():
    # Node-level statistics REST endpoints are not available on ACE 13.
    return ()


def _enrich_flow_resource_statistics(base_url, auth, verify, resource):
    if not isinstance(resource, dict) or resource.get("resource_type") != "ace_message_flow":
        return
    technical_key = _safe_text(resource.get("technical_key"))
    parts = technical_key.split("/")
    if len(parts) < 3:
        return
    server_name, app_name, flow_name = parts[0], parts[1], parts[2]
    for path in _flow_statistics_paths(server_name, app_name, flow_name):
        payload = _rest_get_statistics(
            base_url,
            path,
            auth,
            verify,
            context=technical_key,
        )
        if not payload:
            continue
        _apply_json_statistics_payload([resource], payload)
        properties = _collect_statistics_values(payload)
        if properties:
            _merge_resource_metrics(resource, _flow_statistics_metrics(properties))
        if _resource_has_metric(resource, "message_count") or _resource_has_metric(resource, "error_count"):
            return


def _enrich_server_resource_statistics(base_url, auth, verify, resource):
    if not isinstance(resource, dict) or resource.get("resource_type") != "ace_integration_server":
        return
    server_name = _safe_text(resource.get("technical_key") or resource.get("name"))
    if not server_name:
        return
    for path in _server_statistics_paths(server_name):
        payload = _rest_get_statistics(
            base_url,
            path,
            auth,
            verify,
            context=server_name,
        )
        if not payload:
            continue
        _apply_json_statistics_payload([resource], payload)
        properties = _collect_statistics_values(payload)
        if properties:
            _merge_resource_metrics(resource, _server_statistics_metrics(properties))
        if _resource_has_metric(resource, "memory_used_bytes") or _resource_has_metric(resource, "cpu_percent"):
            return


def _enrich_optadvisor_statistics(thisnode, config, values, result, stat_metrics=None):
    if not isinstance(result, dict):
        return result
    resources = result.get("resources")
    if not isinstance(resources, list) or not resources:
        return result

    base_url = _rest_base_url(thisnode, config, values)
    auth = (values.get("usr", ""), _rest_password(values))
    verify = _rest_verify(config, values)

    for resource in resources:
        if not isinstance(resource, dict):
            continue
        if resource.get("resource_type") == "ace_integration_server":
            _enrich_server_resource_statistics(base_url, auth, verify, resource)
        elif resource.get("resource_type") == "ace_message_flow":
            _enrich_flow_resource_statistics(base_url, auth, verify, resource)

    for path in _snapshot_statistics_paths():
        payload = _rest_get_statistics(
            base_url,
            path,
            auth,
            verify,
            context="node-snapshot",
        )
        if payload:
            _apply_json_statistics_payload(resources, payload)

    _enrich_from_statistics_files(thisnode, config, values, resources, stat_metrics)
    return result


def _rest_collect_optadvisor(thisnode, config, values, stat_metrics=None):
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
                flow_metrics = [common.metric_string("flow_status", flow_status)]
                flow_resource = _resource(
                    "ace_message_flow",
                    server_name + "/" + app_name + "/" + flow_name,
                    flow_name,
                    flow_status,
                    flow_metadata,
                    [metric for metric in flow_metrics if metric],
                    server_name,
                )
                _merge_resource_metrics(
                    flow_resource,
                    _embedded_statistics_metrics(flow, "ace_message_flow"),
                )
                flow_resources.append(flow_resource)

        server_metrics = [common.metric_string("server_status", server_status)]
        _merge_resource_metrics(
            {"metrics": server_metrics},
            _embedded_statistics_metrics(server_data, "ace_integration_server"),
        )
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
        classes.Err("ibmace optadvisor REST discovered no integration servers")
        return None

    return _enrich_optadvisor_statistics(
        thisnode,
        config,
        values,
        {"target": target, "resources": resources},
        stat_metrics,
    )


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
        ret = file_utils.csv_json(file_path, mapping, "", False)
        try:
            retarr = json.loads(ret)
        except (json.JSONDecodeError, TypeError, ValueError):
            retarr = {}
        if not retarr:
            file_utils.truncate_file(file_path)
            continue
        if common.post_stat_payloads(
            "ibmace",
            _rest_statistics_subtype(subtype),
            website,
            webssl,
            retarr,
        ):
            file_utils.truncate_file(file_path)
        else:
            classes.Err("ibmace REST stat upload failed, keeping file for retry:" + str(file_path))


def buildOptAdvisorPayload(thisnode, config, collect_result, collected_at=None):
    if not _optadvisor_enabled(config):
        return None
    if not isinstance(collect_result, dict):
        classes.Err("ibmace optadvisor collector error: invalid collect result")
        return None
    if collect_result.get("err") == "yes" or collect_result.get("error") == "yes":
        message = _safe_text(
            collect_result.get("errorlog")
            or collect_result.get("log")
            or collect_result.get("message")
            or collect_result.get("error")
            or "unknown error"
        )[:common.MAX_LOG_BYTES]
        classes.Err("ibmace optadvisor collector error:" + message)
        return None

    server_id = _safe_text(_get_server_id(config, thisnode))
    if not server_id:
        classes.Err("ibmace optadvisor disabled for missing server_id")
        return None

    resources = collect_result.get("resources", [])
    if not isinstance(resources, list) or len(resources) == 0:
        classes.Err("ibmace optadvisor skipped no resources")
        return None
    if len(resources) > common.MAX_OPTADVISOR_RESOURCES:
        classes.Err("ibmace optadvisor resource batch trimmed to " + str(common.MAX_OPTADVISOR_RESOURCES))
        resources = resources[:common.MAX_OPTADVISOR_RESOURCES]

    node_id = "".join(ch if ch.isalnum() or ch in ("_", "-", ".") else "-" for ch in str(thisnode))[:24]
    payload = {
        "schema_version": OPTADVISOR_SCHEMA_VERSION,
        "collected_at": _iso_utc(collected_at),
        "server_id": server_id,
        "technology": OPTADVISOR_TECHNOLOGY,
        "collector": {
            "name": OPTADVISOR_COLLECTOR_NAME,
            "version": str(config.get("optadvisor_collector_version") or OPTADVISOR_COLLECTOR_VERSION),
            "execution_id": "ibmace-" + node_id + "-" + uuid.uuid4().hex[:22],
            "type": "local",
            "execution_host": socket.gethostname(),
        },
        "target": collect_result.get("target", {}),
        "resources": resources,
    }
    return payload


def _collect_optadvisor(thisnode, config, values, stat_metrics=None):
    classes.Err("ibmace optadvisor REST start:" + str(thisnode))
    rest_result = _rest_collect_optadvisor(thisnode, config, values, stat_metrics)
    if rest_result is None:
        classes.Err("ibmace optadvisor REST collection failed for:" + str(thisnode))
        return
    payload = buildOptAdvisorPayload(thisnode, config, rest_result, _utc_now())
    if payload is not None:
        _append_optadvisor_payload(thisnode, payload)


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
            _collect_optadvisor(thisqm, optadvisor_config, values, _get_applstat_metrics(thisqm, metrics))

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
                if not makerequest._optadvisor_post_accepted(res):
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
        lambda logdir, subtype: _resource_stats_pattern(logdir, thisnode, subtype),
    )
    flushOptAdvisorTelemetry(thisnode, website, webssl, _legacy_token, stat_data)
