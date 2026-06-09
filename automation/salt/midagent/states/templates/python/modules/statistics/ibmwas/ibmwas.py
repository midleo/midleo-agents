import json
import os
import subprocess
from datetime import datetime

from modules.base import classes
from modules.statistics import common

OPTADVISOR_COLLECTOR_NAME = "ibmwas-adminclient-collector"
OPTADVISOR_TECHNOLOGY = "ibmwas"
OPTADVISOR_CONFIG_KEYS = {"appsrv", "appserver", "managed_server", "optadvisor_technology"}


def _resource(resource_type, technical_key, name, status="unknown", metadata=None, metrics=None):
    return {
        "resource_type": resource_type,
        "technical_key": common.safe_text(technical_key),
        "name": common.safe_text(name or technical_key),
        "status": common.safe_text(status or "unknown"),
        "metadata": metadata or {},
        "metrics": metrics or [],
    }


def _technology(config):
    value = common.safe_text(config.get("optadvisor_technology")).lower()
    if value in ("ibmwas", "liberty"):
        return value
    return OPTADVISOR_TECHNOLOGY


def _appserver(config, thisnode):
    return config.get("appsrv") or config.get("appserver") or config.get("managed_server") or "*"


def _load_java_json(command, label):
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
        classes.Err(label + " optadvisor timed out after " + str(common.DEFAULT_TIMEOUT_SECONDS) + " seconds")
        return None
    except OSError as err:
        classes.Err(label + " optadvisor failed to start:" + str(err))
        return None
    if result.stderr:
        classes.Err(label + " optadvisor Error:" + result.stderr[-common.MAX_LOG_BYTES:])
    if result.returncode != 0:
        classes.Err(label + " optadvisor failed with exit code " + str(result.returncode))
        return None
    line = common.java_payload_line(result.stdout)
    if not line:
        return None
    try:
        return json.loads(line)
    except (json.JSONDecodeError, TypeError, ValueError) as err:
        classes.Err(label + " optadvisor payload parse error:" + str(err))
        return None


def _java_command(thisnode, values, config, jar_path, function):
    return [
        "java",
        "-cp",
        "/midleolibs/libs/*:/midleolibs/vendor/*:" + jar_path,
        "midleo_ibmwas.ibmwas_main",
        json.dumps(
            {
                "server": thisnode,
                "appsrv": _appserver(config, thisnode),
                "function": function,
                "usr": values["usr"],
                "pwd": values["pwd"],
                "soapport": values["soapport"],
                "ssl": values["ssl"],
            }
        ),
    ]


def _build_from_results(thisnode, config, metrics_result=None, apps_result=None):
    technology = _technology(config)
    prefix = "liberty" if technology == "liberty" else "ibmwas"
    resources = []
    target = {"status": "running", "server_name": common.safe_text(_appserver(config, thisnode))}

    if isinstance(metrics_result, dict) and metrics_result.get("error") != "yes":
        result = metrics_result.get("result", {})
        base = result.get("base", {}) if isinstance(result, dict) else {}
        vendor = result.get("vendor", {}) if isinstance(result, dict) else {}

        used_heap = common.numeric_value(base.get("memory.usedHeap"))
        max_heap = common.numeric_value(base.get("memory.maxHeap"))
        heap_util = common.numeric_value(vendor.get("memory.heapUtilization"))
        jvm_metrics = []
        if used_heap is not None:
            common.add_metric(jvm_metrics, common.metric_number("heap_used_bytes", used_heap))
        if heap_util is not None:
            common.add_metric(jvm_metrics, common.metric_number("heap_used_percent", heap_util * 100.0 if heap_util <= 1 else heap_util))
        elif used_heap is not None and max_heap and max_heap > 0:
            common.add_metric(jvm_metrics, common.metric_number("heap_used_percent", used_heap * 100.0 / max_heap))
        if technology == "liberty":
            cpu = common.numeric_value(base.get("os.processCpuLoad"))
            if cpu is not None:
                common.add_metric(jvm_metrics, common.metric_number("process_cpu_load", cpu * 100.0 if cpu <= 1 else cpu))
        if jvm_metrics:
            resources.append(_resource(prefix + "_jvm", str(thisnode) + "/jvm", "JVM", "running", {}, jvm_metrics))

        thread_values = {}
        for key, value in vendor.items():
            if key.startswith("threadpool."):
                pool = common.tag_value(key, "pool") or "default"
                thread_values.setdefault(pool, {})
                thread_values[pool][key.split(";", 1)[0]] = value
        for pool, values in thread_values.items():
            metrics = []
            if technology == "liberty":
                common.add_metric(metrics, common.metric_number("active_threads", values.get("threadpool.activeThreads")))
                common.add_metric(metrics, common.metric_number("pool_size", values.get("threadpool.size")))
                resource_type = "liberty_thread_pool"
            else:
                common.add_metric(metrics, common.metric_number("active_count", values.get("threadpool.activeThreads")))
                common.add_metric(metrics, common.metric_number("pool_size", values.get("threadpool.size")))
                resource_type = "ibmwas_thread_pool"
            if metrics:
                resources.append(_resource(resource_type, str(thisnode) + "/" + pool, pool, "running", {"pool": pool}, metrics))

    if isinstance(apps_result, dict) and apps_result.get("error") != "yes":
        app_rows = apps_result.get("applications") or apps_result.get("apps") or apps_result.get("result") or []
        if isinstance(app_rows, dict):
            app_rows = app_rows.values()
        for app in app_rows:
            if not isinstance(app, dict):
                continue
            name = common.safe_text(common.first_present(app, "name", "appname", "application", "displayName"))
            if not name:
                continue
            status = common.first_present(app, "status", "state", "started") or "unknown"
            metric_key = "application_status" if technology == "liberty" else "application_status"
            resources.append(_resource(prefix + ("_application" if technology == "liberty" else "_deployment"), str(thisnode) + "/" + name, name, status, {}, [common.metric_string(metric_key, status)]))

    return target, resources


def _direct_optadvisor_result(result):
    if isinstance(result, dict) and result.get("error") != "yes" and isinstance(result.get("resources"), list):
        target = result.get("target") if isinstance(result.get("target"), dict) else {"status": "running"}
        return target, result.get("resources")
    return None, None


def buildOptAdvisorPayload(thisnode, config, metrics_result=None, apps_result=None, collected_at=None):
    target, resources = _build_from_results(thisnode, config, metrics_result, apps_result)
    return common.build_optadvisor_payload(
        "ibmwas",
        _technology(config),
        OPTADVISOR_COLLECTOR_NAME,
        thisnode,
        config,
        target,
        resources,
        collected_at,
    )


def _collect_optadvisor(thisnode, config, values, jar_path):
    direct_result = _load_java_json(_java_command(thisnode, values, config, jar_path, "getoptadvisor"), "ibmwas")
    target, resources = _direct_optadvisor_result(direct_result)
    if resources is not None:
        payload = common.build_optadvisor_payload(
            "ibmwas",
            _technology(config),
            OPTADVISOR_COLLECTOR_NAME,
            thisnode,
            config,
            target,
            resources,
            common.utc_now(),
        )
        if payload is not None:
            common.append_optadvisor_payload("ibmwas", thisnode, payload)
        return

    metrics_result = _load_java_json(_java_command(thisnode, values, config, jar_path, "metrics"), "ibmwas")
    apps_result = _load_java_json(_java_command(thisnode, values, config, jar_path, "applist"), "ibmwas")
    payload = buildOptAdvisorPayload(thisnode, config, metrics_result, apps_result, common.utc_now())
    if payload is not None:
        common.append_optadvisor_payload("ibmwas", thisnode, payload)


def _ibmwas_rest_path(subtype):
    subtype = str(subtype or "").strip()
    if subtype.startswith("/"):
        return subtype
    paths = {
        "JVM": "/IBMJMXConnectorREST/mbeans/WebSphere:type=JVM,name=JVM,*/attributes",
        "WMQJCAResourceAdapter": "/IBMJMXConnectorREST/mbeans/WebSphere:type=ThreadPool,name=WMQJCAResourceAdapter,*/attributes",
        "MessageListenerThreadPool": "/IBMJMXConnectorREST/mbeans/WebSphere:type=ThreadPool,name=MessageListenerThreadPool,*/attributes",
        "AriesThreadPool": "/IBMJMXConnectorREST/mbeans/WebSphere:type=ThreadPool,name=AriesThreadPool,*/attributes",
        "HAManager.thread.pool": "/IBMJMXConnectorREST/mbeans/WebSphere:type=ThreadPool,name=HAManager.thread.pool,*/attributes",
        "SoapConnectorThreadPool": "/IBMJMXConnectorREST/mbeans/WebSphere:type=ThreadPool,name=SoapConnectorThreadPool,*/attributes",
        "ORB.thread.pool": "/IBMJMXConnectorREST/mbeans/WebSphere:type=ThreadPool,name=ORB.thread.pool,*/attributes",
        "SessionManager": "/IBMJMXConnectorREST/mbeans/WebSphere:type=SessionManager,name=ORB.thread.pool,*/attributes",
    }
    if subtype in paths:
        return paths[subtype]
    return "/IBMJMXConnectorREST/mbeans/WebSphere:feature=kernel,name=ServerInfo/attributes"


def _legacy_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _legacy_number(value):
    number = common.numeric_value(value)
    if number is None:
        return None
    return "{:,.2f}".format(float(number))


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


def _ibmwas_attributes(payload):
    attrs = {}

    def add_pair(name, value):
        name = common.safe_text(name)
        if name:
            attrs[name] = value

    def walk(value):
        if isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            name = value.get("name") or value.get("Name") or value.get("attribute") or value.get("Attribute")
            if name and ("value" in value or "Value" in value):
                add_pair(name, value.get("value") if "value" in value else value.get("Value"))
                return
            for key in ("attributes", "Attributes", "result", "data", "value", "Value"):
                if key in value:
                    walk(value[key])
            for key, item in value.items():
                if key not in ("attributes", "Attributes", "result", "data", "value", "Value"):
                    add_pair(key, item)

    walk(payload)
    return attrs


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


def _write_ibmwas_rest_legacy(logdir, subtype, thisnode, payload):
    attrs = _ibmwas_attributes(payload)
    timestamp = _legacy_timestamp()
    wrote = False

    if str(subtype) == "JVM":
        total = _case_value(attrs, ("getTotalMemory", "totalMemory", "TotalMemory", "heapSize", "maxHeap"))
        free = _case_value(attrs, ("getFreeMemory", "freeMemory", "FreeMemory"))
        wrote = _write_legacy_stat_row(logdir, subtype, "getTotalMemory", thisnode, timestamp, total) or wrote
        wrote = _write_legacy_stat_row(logdir, subtype, "getFreeMemory", thisnode, timestamp, free) or wrote
        return wrote

    for key, value in attrs.items():
        wrote = _write_legacy_stat_row(logdir, subtype, key, thisnode, timestamp, value) or wrote
    return wrote


def _collect_rest_statistics(thisnode, values, metrics):
    base_url, _ = common.rest_base_url(thisnode, values, values.get("port") or "9443")
    for subtype, logdir in metrics.items():
        try:
            payload = common.rest_json_request(base_url, _ibmwas_rest_path(subtype), values)
            if not _write_ibmwas_rest_legacy(logdir, subtype, thisnode, payload):
                common.write_numeric_tree(logdir, subtype, thisnode, payload)
        except Exception as err:
            classes.Err("ibmwas rest statistics error:" + str(err))


def restAvailabilityCheck(thisnode, values):
    base_url, _ = common.rest_base_url(thisnode, values, values.get("port") or "9443")
    try:
        payload = common.rest_json_request(
            base_url,
            "/IBMJMXConnectorREST/mbeans/WebSphere:feature=kernel,name=ServerInfo/attributes",
            values,
        )
    except Exception:
        return 0
    if isinstance(payload, list) and payload:
        return 1
    if isinstance(payload, dict) and (payload.get("value") or payload.get("Name") or payload.get("attributes")):
        return 1
    return 0


def getStat(thisqm, inpdata):
    try:
        inpdata = common.parse_json_object(inpdata)
        values, metrics = common.pop_fields(
            inpdata,
            {
                "usr": "",
                "pwd": "",
                "soapport": "",
                "mngmport": "",
                "port": "",
                "webport": "",
                "host": "",
                "ssl": "no",
                "conntype": "jms",
            },
        )
        if not values.get("soapport"):
            values["soapport"] = values.get("mngmport") or values.get("port") or values.get("webport") or ""
        optadvisor_config, metrics = common.split_optadvisor_config(metrics, OPTADVISOR_CONFIG_KEYS)
        jar_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "resources",
            "midleo_ibmwas.jar",
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
                    "soapport": values["soapport"],
                    "ssl": values["ssl"],
                }
            )

            common.run_command(
                [
                    "java",
                    "-cp",
                    "/midleolibs/libs/*:/midleolibs/vendor/*:" + jar_path,
                    "midleo_ibmwas.ibmwas_main",
                    java_arg,
                ],
                "ibmwas",
            )

        if common.optadvisor_collection_enabled(optadvisor_config):
            _collect_optadvisor(thisqm, optadvisor_config, values, jar_path)

    except (json.JSONDecodeError, TypeError, ValueError) as err:
        classes.Err("Error in ibmwas statistics:" + str(err))


def resetStat(thisnode, website, webssl, _legacy_token, stat_data):
    _, legacy_stat_data = common.split_optadvisor_config(stat_data if isinstance(stat_data, dict) else {}, OPTADVISOR_CONFIG_KEYS)
    common.post_csv_stats(
        "ibmwas",
        "ibmwas",
        website,
        webssl,
        _legacy_token,
        legacy_stat_data,
        lambda logdir, subtype: logdir + "Statistics_" + subtype + ".csv",
    )
    common.flush_optadvisor_telemetry("ibmwas", thisnode, website, webssl, _legacy_token, stat_data, OPTADVISOR_CONFIG_KEYS)
