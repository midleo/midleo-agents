import json
import os
import socket
import subprocess
import uuid
from datetime import datetime, timezone

from modules.base import classes, makerequest
from modules.statistics import common


OPTADVISOR_SCHEMA_VERSION = "1.0"
OPTADVISOR_COLLECTOR_NAME = "jboss-wildfly-management-collector"
OPTADVISOR_COLLECTOR_VERSION = "1.0.0"
OPTADVISOR_DEFAULT_TECHNOLOGY = "jboss"
OPTADVISOR_CONFIG_KEYS = {
    "optadvisor",
    "optadvisor_enabled",
    "optimization_advisor",
    "optadvisor_collector_version",
    "optadvisor_technology",
    "appcode",
    "appsrvid",
    "server_id",
    "serverid",
    "srvid",
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


def _technology(config):
    value = _safe_text(config.get("optadvisor_technology")).lower()
    if value in ("jboss", "wildfly"):
        return value
    return OPTADVISOR_DEFAULT_TECHNOLOGY


def _get_server_id(config, thisnode):
    return (
        config.get("server_id")
        or config.get("appsrvid")
        or config.get("serverid")
        or config.get("srvid")
        or thisnode
    )


def _optadvisor_log_path(thisnode):
    return os.path.join(os.getcwd(), "logs", "jboss_" + str(thisnode) + "_optadvisor.jsonl")


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
    if not isinstance(java_result, dict) or java_result.get("error") == "yes":
        return None

    appcode = _safe_text(config.get("appcode"))
    server_id = _safe_text(_get_server_id(config, thisnode))
    if not server_id:
        classes.Err("jboss optadvisor disabled for missing server_id")
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
        "technology": _technology(config),
        "collector": {
            "name": OPTADVISOR_COLLECTOR_NAME,
            "version": str(config.get("optadvisor_collector_version") or OPTADVISOR_COLLECTOR_VERSION),
            "execution_id": "jboss-" + node_id + "-" + uuid.uuid4().hex[:24],
            "type": "local",
            "execution_host": socket.gethostname(),
        },
        "target": java_result.get("target", {}),
        "resources": resources,
    }


def _collect_optadvisor(thisnode, config, values, jar_path):
    java_arg = json.dumps(
        {
            "server": thisnode,
            "function": "getoptadvisor",
            "usr": values["usr"],
            "pwd": values["pwd"],
            "mngmport": values["mngmport"],
        }
    )
    command = [
        "java",
        "-cp",
        "/midleolibs/libs/*:" + jar_path,
        "midleo_jboss.midleo_jboss",
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
        classes.Err("jboss optadvisor timed out after " + str(common.DEFAULT_TIMEOUT_SECONDS) + " seconds")
        return
    except OSError as err:
        classes.Err("jboss optadvisor failed to start:" + str(err))
        return

    if result.stderr:
        classes.Err("jboss optadvisor Error:" + result.stderr[-common.MAX_LOG_BYTES:])
    if result.returncode != 0:
        classes.Err("jboss optadvisor failed with exit code " + str(result.returncode))
        return

    try:
        payload_line = _java_payload_line(result.stdout)
        if not payload_line:
            classes.Err("jboss optadvisor returned no JSON payload")
            return
        java_result = json.loads(payload_line)
        payload = buildOptAdvisorPayload(thisnode, config, java_result, _utc_now())
        if payload is not None:
            _append_optadvisor_payload(thisnode, payload)
    except (json.JSONDecodeError, TypeError, ValueError) as err:
        classes.Err("jboss optadvisor payload parse error:" + str(err))


def _management_address(value):
    text = str(value or "").strip()
    if not text.startswith("/"):
        return []
    address = []
    for item in text.strip("/").split("/"):
        if "=" not in item:
            continue
        key, val = item.split("=", 1)
        if key and val:
            address.append({key: val})
    return address


JBOSS_REST_SIMPLE_FIELDS = {
    "Threading": ("/core-service=platform-mbean/type=threading", ("thread-count", "ThreadCount")),
    "ThreadingPeak": ("/core-service=platform-mbean/type=threading", ("peak-thread-count", "PeakThreadCount")),
    "ThreadingDaemon": ("/core-service=platform-mbean/type=threading", ("daemon-thread-count", "DaemonThreadCount")),
    "ClassLoading": ("/core-service=platform-mbean/type=class-loading", ("loaded-class-count", "LoadedClassCount")),
    "ClassLoadingTotal": ("/core-service=platform-mbean/type=class-loading", ("total-loaded-class-count", "TotalLoadedClassCount")),
    "ClassLoadingUnloaded": ("/core-service=platform-mbean/type=class-loading", ("unloaded-class-count", "UnloadedClassCount")),
    "OSProcessCpuLoad": ("/core-service=platform-mbean/type=operating-system", ("process-cpu-load", "ProcessCpuLoad")),
    "OSSystemCpuLoad": ("/core-service=platform-mbean/type=operating-system", ("system-cpu-load", "SystemCpuLoad")),
    "OSFreePhysicalMemory": ("/core-service=platform-mbean/type=operating-system", ("free-physical-memory-size", "FreePhysicalMemorySize")),
    "DatasourceActiveCount": ("/subsystem=datasources/data-source=ExampleDS/statistics=pool", ("ActiveCount", "active-count")),
    "DatasourceInUseCount": ("/subsystem=datasources/data-source=ExampleDS/statistics=pool", ("InUseCount", "in-use-count")),
    "DatasourceAvailableCount": ("/subsystem=datasources/data-source=ExampleDS/statistics=pool", ("AvailableCount", "available-count")),
    "UndertowRequestCount": ("/subsystem=undertow/server=default-server/http-listener=default", ("RequestCount", "request-count")),
    "UndertowErrorCount": ("/subsystem=undertow/server=default-server/http-listener=default", ("ErrorCount", "error-count")),
    "G1YoungGenCollectionCount": ("/core-service=platform-mbean/type=garbage-collector/name=G1 Young Generation", ("collection-count", "CollectionCount")),
    "G1YoungGenCollectionTime": ("/core-service=platform-mbean/type=garbage-collector/name=G1 Young Generation", ("collection-time", "CollectionTime")),
    "G1OldGenCollectionCount": ("/core-service=platform-mbean/type=garbage-collector/name=G1 Old Generation", ("collection-count", "CollectionCount")),
    "G1OldGenCollectionTime": ("/core-service=platform-mbean/type=garbage-collector/name=G1 Old Generation", ("collection-time", "CollectionTime")),
}


def _rest_address_for_subtype(subtype):
    if str(subtype).startswith("/"):
        return subtype
    if str(subtype) in ("MemoryHeapMemoryUsage", "MemoryNonHeapMemoryUsage"):
        return "/core-service=platform-mbean/type=memory"
    config = JBOSS_REST_SIMPLE_FIELDS.get(str(subtype))
    return config[0] if config else ""


def _legacy_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _legacy_number(value):
    number = common.numeric_value(value)
    if number is None:
        return None
    return str(int(number)) if float(number).is_integer() else str(number)


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


def _write_legacy_stat_row(logdir, subtype, key, server, timestamp, value):
    formatted = _legacy_number(value)
    if formatted is None:
        return False
    os.makedirs(str(logdir), exist_ok=True)
    file_path = os.path.join(str(logdir), "Statistics_" + str(subtype) + ".csv")
    new_file = not os.path.isfile(file_path) or os.path.getsize(file_path) == 0
    with open(file_path, "a", encoding="utf-8", newline="") as f:
        if new_file:
            f.write("key,server,timestamp,value\n")
        f.write(str(key) + "," + str(server) + "," + str(timestamp) + "," + formatted + "\n")
    return True


def _write_jboss_memory_usage(logdir, subtype, thisnode, result):
    field = "heap-memory-usage" if str(subtype) == "MemoryHeapMemoryUsage" else "non-heap-memory-usage"
    usage = result.get(field) if isinstance(result, dict) and isinstance(result.get(field), dict) else {}
    timestamp = _legacy_timestamp()
    wrote = False
    for key in ("committed", "init", "max", "used"):
        value = common.numeric_value(_case_value(usage, (key, key.replace("-", "_"))))
        if value is None:
            continue
        wrote = _write_legacy_stat_row(logdir, subtype, key + "_mb", thisnode, timestamp, value / 1048576) or wrote
    return wrote


def _write_jboss_rest_legacy(logdir, subtype, thisnode, payload):
    result = payload.get("result") if isinstance(payload, dict) and isinstance(payload.get("result"), dict) else {}
    if str(subtype) in ("MemoryHeapMemoryUsage", "MemoryNonHeapMemoryUsage"):
        return _write_jboss_memory_usage(logdir, subtype, thisnode, result)
    config = JBOSS_REST_SIMPLE_FIELDS.get(str(subtype))
    if not config:
        return False
    value = _case_value(result, config[1])
    return _write_legacy_stat_row(logdir, subtype, subtype, thisnode, _legacy_timestamp(), value)


def _collect_rest_statistics(thisnode, values, metrics):
    base_url, _ = common.rest_base_url(thisnode, values, values.get("port") or "9990")
    for subtype, logdir in metrics.items():
        request_payload = {
            "operation": "read-resource",
            "include-runtime": True,
            "recursive": True,
        }
        address = _management_address(_rest_address_for_subtype(subtype))
        if address:
            request_payload["address"] = address
        try:
            payload = common.rest_json_request(
                base_url,
                "/management",
                values,
                method="POST",
                payload=request_payload,
                auth="digest",
            )
            if not _write_jboss_rest_legacy(logdir, subtype, thisnode, payload):
                common.write_numeric_tree(logdir, subtype, thisnode, payload)
        except Exception as err:
            classes.Err("jboss rest statistics error:" + str(err))


def restAvailabilityCheck(thisnode, values):
    base_url, _ = common.rest_base_url(thisnode, values, values.get("port") or "9990")
    try:
        payload = common.rest_json_request(
            base_url,
            "/management",
            values,
            method="POST",
            payload={"operation": "read-resource", "include-runtime": True},
            auth="digest",
        )
    except Exception:
        return 0
    result = payload.get("result") if isinstance(payload, dict) else {}
    if not isinstance(result, dict):
        return 0
    state = result.get("server-state") or result.get("state") or result.get("status")
    return 1 if common.safe_text(state).lower() == "running" else 0


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
        jar_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "resources",
            "midleo_jboss.jar",
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
                }
            )

            common.run_command(
                [
                    "java",
                    "-cp",
                    "/midleolibs/libs/*:" + jar_path,
                    "midleo_jboss.midleo_jboss",
                    java_arg,
                ],
                "jboss",
            )

        if common.optadvisor_collection_enabled(optadvisor_config):
            _collect_optadvisor(thisqm, optadvisor_config, values, jar_path)

    except (json.JSONDecodeError, TypeError, ValueError) as err:
        classes.Err("Error in jboss statistics:" + str(err))


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
                classes.Err("jboss optadvisor payload parse error:" + str(err))
            except Exception as err:
                classes.Err("jboss optadvisor post error:" + str(err))
                remaining.append(line)

        with open(file, "w", encoding="utf-8") as f:
            f.writelines(remaining)
    except OSError as err:
        classes.Err("jboss optadvisor file error:" + str(err))


def resetStat(thisnode, website, webssl, _legacy_token, stat_data):
    _, legacy_stat_data = _split_optadvisor_config(stat_data if isinstance(stat_data, dict) else {})
    common.post_csv_stats(
        "jboss",
        "jboss",
        website,
        webssl,
        _legacy_token,
        legacy_stat_data,
        lambda logdir, subtype: logdir + "Statistics_" + subtype + ".csv",
    )
    flushOptAdvisorTelemetry(thisnode, website, webssl, _legacy_token, stat_data)
