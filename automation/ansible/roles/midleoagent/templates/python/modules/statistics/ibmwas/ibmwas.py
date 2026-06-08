import json
import os
import subprocess

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


def getStat(thisqm, inpdata):
    try:
        inpdata = common.parse_json_object(inpdata)
        values, metrics = common.pop_fields(
            inpdata, {"usr": "", "pwd": "", "soapport": "", "ssl": "no"}
        )
        optadvisor_config, metrics = common.split_optadvisor_config(metrics, OPTADVISOR_CONFIG_KEYS)
        jar_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "resources",
            "midleo_ibmwas.jar",
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
