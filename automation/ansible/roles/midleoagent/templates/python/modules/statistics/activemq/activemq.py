import json
import os
import subprocess

from modules.base import classes
from modules.statistics import common

OPTADVISOR_COLLECTOR_NAME = "activemq-jmx-collector"
OPTADVISOR_TECHNOLOGY = "activemq"
ACTIVEMQ_CONFIG_KEYS = {"broker", "jmxport"}


def _resource(resource_type, technical_key, name, status="unknown", metadata=None, metrics=None):
    return {
        "resource_type": resource_type,
        "technical_key": common.safe_text(technical_key),
        "name": common.safe_text(name or technical_key),
        "status": common.safe_text(status or "unknown"),
        "metadata": metadata or {},
        "metrics": metrics or [],
    }


def _broker_name(config, thisnode):
    return config.get("broker") or thisnode


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
        "/midleolibs/libs/*:" + jar_path,
        "midleo_activemq.activemq_main",
        json.dumps(
            {
                "server": thisnode,
                "function": function,
                "usr": values["usr"],
                "pwd": values["pwd"],
                "jmxport": values["mngmport"],
                "broker": _broker_name(config, thisnode),
            }
        ),
    ]


def _build_from_results(thisnode, config, srvinfo=None, queues=None, topics=None, connections=None):
    resources = []
    target = {"status": "running", "broker": common.safe_text(_broker_name(config, thisnode))}
    broker_name = common.safe_text(_broker_name(config, thisnode))
    broker_metrics = []

    if isinstance(srvinfo, dict) and srvinfo.get("error") != "yes":
        info = srvinfo.get("serverinfo", {})
        if isinstance(info, dict):
            status = info.get("status") or "online"
            target["status"] = common.safe_text(status).lower()
            if info.get("version"):
                target["version"] = common.safe_text(info.get("version"))
            common.add_metric(broker_metrics, common.metric_string("broker_status", status))

    if isinstance(connections, list):
        common.add_metric(broker_metrics, common.metric_number("current_connections_count", len(connections)))

    if broker_metrics:
        resources.append(_resource("activemq_broker", broker_name, broker_name, target.get("status", "running"), {}, broker_metrics))

    if isinstance(queues, list):
        for queue in queues:
            if not isinstance(queue, dict):
                continue
            name = common.safe_text(queue.get("name"))
            if not name:
                continue
            metrics = []
            common.add_metric(metrics, common.metric_number("queue_size", common.first_present(queue, "size", "queueSize")))
            common.add_metric(metrics, common.metric_number("consumer_count", common.first_present(queue, "consumers", "consumerCount")))
            common.add_metric(metrics, common.metric_number("enqueue_count", common.first_present(queue, "enqueued", "enqueueCount")))
            common.add_metric(metrics, common.metric_number("dequeue_count", common.first_present(queue, "dequeued", "dequeueCount")))
            if metrics:
                resources.append(_resource("activemq_queue", broker_name + "/queue/" + name, name, "running", {}, metrics))

    if isinstance(topics, list):
        for topic in topics:
            if not isinstance(topic, dict):
                continue
            name = common.safe_text(topic.get("name"))
            if not name:
                continue
            metrics = []
            common.add_metric(metrics, common.metric_number("queue_size", common.first_present(topic, "size", "queueSize")))
            common.add_metric(metrics, common.metric_number("consumer_count", common.first_present(topic, "consumers", "consumerCount")))
            common.add_metric(metrics, common.metric_number("enqueue_count", common.first_present(topic, "enqueued", "enqueueCount")))
            common.add_metric(metrics, common.metric_number("dequeue_count", common.first_present(topic, "dequeued", "dequeueCount")))
            if metrics:
                resources.append(_resource("activemq_topic", broker_name + "/topic/" + name, name, "running", {}, metrics))

    return target, resources


def _direct_optadvisor_result(result):
    if isinstance(result, dict) and result.get("error") != "yes" and isinstance(result.get("resources"), list):
        target = result.get("target") if isinstance(result.get("target"), dict) else {"status": "running"}
        return target, result.get("resources")
    return None, None


def buildOptAdvisorPayload(thisnode, config, srvinfo=None, queues=None, topics=None, connections=None, collected_at=None):
    target, resources = _build_from_results(thisnode, config, srvinfo, queues, topics, connections)
    return common.build_optadvisor_payload(
        "activemq",
        OPTADVISOR_TECHNOLOGY,
        OPTADVISOR_COLLECTOR_NAME,
        thisnode,
        config,
        target,
        resources,
        collected_at,
    )


def _collect_optadvisor(thisnode, config, values, jar_path):
    direct_result = _load_java_json(_java_command(thisnode, values, config, jar_path, "getoptadvisor"), "activemq")
    target, resources = _direct_optadvisor_result(direct_result)
    if resources is not None:
        payload = common.build_optadvisor_payload(
            "activemq",
            OPTADVISOR_TECHNOLOGY,
            OPTADVISOR_COLLECTOR_NAME,
            thisnode,
            config,
            target,
            resources,
            common.utc_now(),
        )
        if payload is not None:
            common.append_optadvisor_payload("activemq", thisnode, payload)
        return

    srvinfo = _load_java_json(_java_command(thisnode, values, config, jar_path, "srvinfo"), "activemq")
    queues = _load_java_json(_java_command(thisnode, values, config, jar_path, "queues"), "activemq")
    topics = _load_java_json(_java_command(thisnode, values, config, jar_path, "topics"), "activemq")
    connections = _load_java_json(_java_command(thisnode, values, config, jar_path, "connections"), "activemq")
    payload = buildOptAdvisorPayload(thisnode, config, srvinfo, queues, topics, connections, common.utc_now())
    if payload is not None:
        common.append_optadvisor_payload("activemq", thisnode, payload)


def getStat(thisqm, inpdata):
    try:
        inpdata = common.parse_json_object(inpdata)
        values, metrics = common.pop_fields(
            inpdata, {"usr": "", "pwd": "", "mngmport": ""}
        )
        optadvisor_config, metrics = common.split_optadvisor_config(metrics, ACTIVEMQ_CONFIG_KEYS)
        jar_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "resources",
            "midleo_activemq.jar",
        )
        if metrics:
            java_arg = json.dumps(
                {
                    "logdir": common.first_value(metrics),
                    "server": thisqm,
                    "mbean": ",".join(metrics.keys()),
                    "function": "localstat",
                    "usr": values["usr"],
                    "pwd": values["pwd"],
                    "jmxport": values["mngmport"],
                    "broker": _broker_name(optadvisor_config, thisqm),
                }
            )

            common.run_command(
                [
                    "java",
                    "-cp",
                    "/midleolibs/libs/*:" + jar_path,
                    "midleo_activemq.activemq_main",
                    java_arg,
                ],
                "activemq",
            )

        if common.optadvisor_collection_enabled(optadvisor_config):
            _collect_optadvisor(thisqm, optadvisor_config, values, jar_path)

    except (json.JSONDecodeError, TypeError, ValueError) as err:
        classes.Err("Error in activemq statistics:" + str(err))


def resetStat(thisnode, website, webssl, _legacy_token, stat_data):
    _, legacy_stat_data = common.split_optadvisor_config(stat_data if isinstance(stat_data, dict) else {}, ACTIVEMQ_CONFIG_KEYS)
    common.post_csv_stats(
        "activemq",
        "activemq",
        website,
        webssl,
        _legacy_token,
        legacy_stat_data,
        lambda logdir, subtype: logdir + "Statistics_" + subtype + ".csv",
    )
    common.flush_optadvisor_telemetry("activemq", thisnode, website, webssl, _legacy_token, stat_data, ACTIVEMQ_CONFIG_KEYS)
