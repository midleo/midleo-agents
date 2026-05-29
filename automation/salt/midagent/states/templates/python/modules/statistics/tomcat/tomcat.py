import json
import os
import subprocess

from modules.base import classes
from modules.statistics import common

OPTADVISOR_COLLECTOR_NAME = "tomcat-jmx-collector"
OPTADVISOR_TECHNOLOGY = "tomcat"


def _resource(resource_type, technical_key, name, status="unknown", metadata=None, metrics=None):
    return {
        "resource_type": resource_type,
        "technical_key": common.safe_text(technical_key),
        "name": common.safe_text(name or technical_key),
        "status": common.safe_text(status or "unknown"),
        "metadata": metadata or {},
        "metrics": metrics or [],
    }


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


def _java_command(thisnode, values, jar_path, function):
    return [
        "java",
        "-cp",
        "/midleolibs/libs/*:" + jar_path,
        "midleo_tomcat.midleo_tomcat",
        json.dumps(
            {
                "server": thisnode,
                "function": function,
                "usr": values["usr"],
                "pwd": values["pwd"],
                "mngmport": values["mngmport"],
            }
        ),
    ]


def _build_from_results(thisnode, metrics_result=None, datasources_result=None, apps_result=None):
    resources = []
    target = {"status": "running"}

    if isinstance(metrics_result, dict) and metrics_result.get("error") != "yes":
        result = metrics_result.get("result", {})
        base = result.get("base", {}) if isinstance(result, dict) else {}
        vendor = result.get("vendor", {}) if isinstance(result, dict) else {}

        heap_used = common.numeric_value(base.get("memory.heap.used"))
        heap_max = common.numeric_value(base.get("memory.heap.max"))
        heap_metrics = []
        if heap_used is not None:
            common.add_metric(heap_metrics, common.metric_number("heap_used_bytes", heap_used))
        if heap_used is not None and heap_max and heap_max > 0:
            common.add_metric(heap_metrics, common.metric_number("heap_used_percent", heap_used * 100.0 / heap_max))
        process_cpu = common.numeric_value(base.get("os.processCpuLoad"))
        if process_cpu is not None:
            common.add_metric(heap_metrics, common.metric_number("process_cpu_load", process_cpu * 100.0 if process_cpu <= 1 else process_cpu))
        if heap_metrics:
            resources.append(_resource("tomcat_jvm", str(thisnode) + "/jvm", "Tomcat JVM", "running", {}, heap_metrics))

        thread_metrics_by_connector = {}
        http_metrics_by_connector = {}
        for key, value in vendor.items():
            if key.startswith("threadpool."):
                connector = common.tag_value(key, "connector") or "default"
                thread_metrics_by_connector.setdefault(connector, {})
                metric_name = key.split(";", 1)[0]
                thread_metrics_by_connector[connector][metric_name] = value
            elif key.startswith("http."):
                connector = common.tag_value(key, "connector") or "default"
                http_metrics_by_connector.setdefault(connector, {})
                metric_name = key.split(";", 1)[0]
                http_metrics_by_connector[connector][metric_name] = value

        for connector, values in thread_metrics_by_connector.items():
            metrics = []
            common.add_metric(metrics, common.metric_number("current_threads_busy", values.get("threadpool.busy")))
            common.add_metric(metrics, common.metric_number("current_thread_count", values.get("threadpool.current")))
            common.add_metric(metrics, common.metric_number("max_threads", values.get("threadpool.max")))
            if metrics:
                resources.append(_resource("tomcat_thread_pool", str(thisnode) + "/" + connector, connector, "running", {"connector": connector}, metrics))

        for connector, values in http_metrics_by_connector.items():
            metrics = []
            common.add_metric(metrics, common.metric_number("request_count", values.get("http.requestCount")))
            common.add_metric(metrics, common.metric_number("error_count", values.get("http.errorCount")))
            common.add_metric(metrics, common.metric_number("processing_time_ms", values.get("http.processingTime")))
            if metrics:
                resources.append(_resource("tomcat_connector", str(thisnode) + "/" + connector, connector, "running", {"connector": connector}, metrics))

    if isinstance(datasources_result, dict) and datasources_result.get("error") != "yes":
        for ds in datasources_result.get("datasources", []) or []:
            if not isinstance(ds, dict):
                continue
            name = common.safe_text(common.first_present(ds, "name", "jndiName", "objectName"))
            if not name:
                continue
            metrics = []
            common.add_metric(metrics, common.metric_number("active_connections", common.first_present(ds, "numActive", "active", "activeCount")))
            common.add_metric(metrics, common.metric_number("idle_connections", common.first_present(ds, "numIdle", "idle", "idleCount")))
            if metrics:
                resources.append(_resource("tomcat_datasource", str(thisnode) + "/" + name, name, common.first_present(ds, "stateName", "state") or "unknown", {}, metrics))

    if isinstance(apps_result, dict) and apps_result.get("error") != "yes":
        for app in apps_result.get("applications", []) or []:
            if not isinstance(app, dict):
                continue
            name = common.safe_text(common.first_present(app, "name", "path"))
            if not name:
                continue
            status = common.first_present(app, "status", "stateName") or "unknown"
            metrics = [common.metric_string("deployment_status", status)]
            resources.append(_resource("tomcat_deployment", str(thisnode) + "/" + name, name, status, {"path": common.safe_text(app.get("path"))}, metrics))

    return target, resources


def _direct_optadvisor_result(result):
    if isinstance(result, dict) and result.get("error") != "yes" and isinstance(result.get("resources"), list):
        target = result.get("target") if isinstance(result.get("target"), dict) else {"status": "running"}
        return target, result.get("resources")
    return None, None


def buildOptAdvisorPayload(thisnode, config, metrics_result=None, datasources_result=None, apps_result=None, collected_at=None):
    target, resources = _build_from_results(thisnode, metrics_result, datasources_result, apps_result)
    return common.build_optadvisor_payload(
        "tomcat",
        OPTADVISOR_TECHNOLOGY,
        OPTADVISOR_COLLECTOR_NAME,
        thisnode,
        config,
        target,
        resources,
        collected_at,
    )


def _collect_optadvisor(thisnode, config, values, jar_path):
    direct_result = _load_java_json(_java_command(thisnode, values, jar_path, "getoptadvisor"), "tomcat")
    target, resources = _direct_optadvisor_result(direct_result)
    if resources is not None:
        payload = common.build_optadvisor_payload(
            "tomcat",
            OPTADVISOR_TECHNOLOGY,
            OPTADVISOR_COLLECTOR_NAME,
            thisnode,
            config,
            target,
            resources,
            common.utc_now(),
        )
        if payload is not None:
            common.append_optadvisor_payload("tomcat", thisnode, payload)
        return

    metrics_result = _load_java_json(_java_command(thisnode, values, jar_path, "metrics"), "tomcat")
    datasources_result = _load_java_json(_java_command(thisnode, values, jar_path, "datasources"), "tomcat")
    apps_result = _load_java_json(_java_command(thisnode, values, jar_path, "applist"), "tomcat")
    payload = buildOptAdvisorPayload(thisnode, config, metrics_result, datasources_result, apps_result, common.utc_now())
    if payload is not None:
        common.append_optadvisor_payload("tomcat", thisnode, payload)


def getStat(thisqm, inpdata):
    try:
        inpdata = common.parse_json_object(inpdata)
        values, metrics = common.pop_fields(
            inpdata, {"usr": "", "pwd": "", "mngmport": ""}
        )
        optadvisor_config, metrics = common.split_optadvisor_config(metrics)
        jar_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "resources",
            "midleo_tomcat.jar",
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
                }
            )

            common.run_command(
                [
                    "java",
                    "-cp",
                    "/midleolibs/libs/*:" + jar_path,
                    "midleo_tomcat.midleo_tomcat",
                    java_arg,
                ],
                "tomcat",
            )

        if common.optadvisor_collection_enabled(optadvisor_config):
            _collect_optadvisor(thisqm, optadvisor_config, values, jar_path)

    except (json.JSONDecodeError, TypeError, ValueError) as err:
        classes.Err("Error in tomcat statistics:" + str(err))


def resetStat(thisnode, website, webssl, inttoken, stat_data):
    _, legacy_stat_data = common.split_optadvisor_config(stat_data if isinstance(stat_data, dict) else {})
    common.post_csv_stats(
        "tomcat",
        "tomcat",
        website,
        webssl,
        inttoken,
        legacy_stat_data,
        lambda logdir, subtype: logdir + "Statistics_" + subtype + ".csv",
    )
    common.flush_optadvisor_telemetry("tomcat", thisnode, website, webssl, inttoken, stat_data)
