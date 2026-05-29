import json
import os
import subprocess

from modules.base import classes
from modules.statistics import common

OPTADVISOR_COLLECTOR_NAME = "kafka-admin-jmx-collector"
OPTADVISOR_TECHNOLOGY = "kafka"
KAFKA_CONFIG_KEYS = {
    "port",
    "jmxport",
    "security",
    "username",
    "pwd",
    "sasl_mechanism",
}


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
    payload = {
        "server": thisnode,
        "localbrk": thisnode,
        "function": function,
        "port": values.get("port", "9092"),
        "jmxport": values.get("jmxport", "9999"),
        "security": values.get("security", "PLAINTEXT"),
    }
    if values.get("username"):
        payload["username"] = values.get("username")
    if values.get("pwd"):
        payload["pwd"] = values.get("pwd")
    if values.get("sasl_mechanism"):
        payload["sasl_mechanism"] = values.get("sasl_mechanism")
    return [
        "java",
        "-cp",
        "/midleolibs/libs/*:" + jar_path,
        "midleo_kafka.kafka_main",
        json.dumps(payload),
    ]


def _build_from_results(thisnode, srvinfo=None, topics=None):
    resources = []
    target = {"status": "running"}
    broker_resources = {}
    cluster_id = ""

    if isinstance(srvinfo, dict) and srvinfo.get("error") != "yes":
        broker = srvinfo.get("broker", {})
        if isinstance(broker, dict):
            cluster_id = common.safe_text(broker.get("cluster"))
            broker_resources = broker.get("resources", {}) if isinstance(broker.get("resources"), dict) else {}
            if cluster_id:
                target["cluster_id"] = cluster_id

    broker_metrics = []
    common.add_metric(broker_metrics, common.metric_number("bytes_in_rate", broker_resources.get("Bytes In Per Sec")))
    common.add_metric(broker_metrics, common.metric_number("messages_in_rate", broker_resources.get("Messages In Per Sec")))
    common.add_metric(broker_metrics, common.metric_number("under_replicated_partitions", common.first_present(broker_resources, "Under-replicated (JMX)", "Under-replicated Partitions")))
    common.add_metric(broker_metrics, common.metric_number("topic_count", broker_resources.get("Topics Count")))
    common.add_metric(broker_metrics, common.metric_number("consumer_group_count", broker_resources.get("Consumers Count")))
    if broker_metrics:
        resources.append(_resource("kafka_broker", str(thisnode), str(thisnode), "running", {"cluster_id": cluster_id}, broker_metrics))

    if isinstance(topics, list):
        for topic in topics:
            if not isinstance(topic, dict):
                continue
            name = common.safe_text(topic.get("name"))
            if not name or name.startswith("_"):
                continue
            metrics = []
            common.add_metric(metrics, common.metric_number("messages_in_rate", topic.get("messinpersec")))
            common.add_metric(metrics, common.metric_number("bytes_in_rate", topic.get("bytespersec")))
            common.add_metric(metrics, common.metric_number("partition_count", topic.get("partitions")))
            if metrics:
                metadata = {}
                if "replicationFactor" in topic:
                    metadata["replication_factor"] = common.safe_text(topic.get("replicationFactor"))
                if "retention" in topic:
                    metadata["retention_ms"] = common.safe_text(topic.get("retention"))
                resources.append(_resource("kafka_topic", str(thisnode) + "/" + name, name, "running", metadata, metrics))

    return target, resources


def _direct_optadvisor_result(result):
    if isinstance(result, dict) and result.get("error") != "yes" and isinstance(result.get("resources"), list):
        target = result.get("target") if isinstance(result.get("target"), dict) else {"status": "running"}
        return target, result.get("resources")
    return None, None


def buildOptAdvisorPayload(thisnode, config, srvinfo=None, topics=None, collected_at=None):
    target, resources = _build_from_results(thisnode, srvinfo, topics)
    return common.build_optadvisor_payload(
        "kafka",
        OPTADVISOR_TECHNOLOGY,
        OPTADVISOR_COLLECTOR_NAME,
        thisnode,
        config,
        target,
        resources,
        collected_at,
    )


def _collect_optadvisor(thisnode, config, values, jar_path):
    direct_result = _load_java_json(_java_command(thisnode, values, jar_path, "getoptadvisor"), "kafka")
    target, resources = _direct_optadvisor_result(direct_result)
    if resources is not None:
        payload = common.build_optadvisor_payload(
            "kafka",
            OPTADVISOR_TECHNOLOGY,
            OPTADVISOR_COLLECTOR_NAME,
            thisnode,
            config,
            target,
            resources,
            common.utc_now(),
        )
        if payload is not None:
            common.append_optadvisor_payload("kafka", thisnode, payload)
        return

    srvinfo = _load_java_json(_java_command(thisnode, values, jar_path, "srvinfo"), "kafka")
    topics = _load_java_json(_java_command(thisnode, values, jar_path, "topics"), "kafka")
    payload = buildOptAdvisorPayload(thisnode, config, srvinfo, topics, common.utc_now())
    if payload is not None:
        common.append_optadvisor_payload("kafka", thisnode, payload)


def getStat(thisqm, inpdata):
    try:
        inpdata = common.parse_json_object(inpdata)
        values, metrics = common.pop_fields(
            inpdata,
            {
                "port": "9092",
                "jmxport": "9999",
                "security": "PLAINTEXT",
                "username": "",
                "pwd": "",
                "sasl_mechanism": "",
            },
        )
        optadvisor_config, metrics = common.split_optadvisor_config(metrics, KAFKA_CONFIG_KEYS)
        jar_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "resources",
            "midleo_kafka.jar",
        )
        if metrics:
            java_arg_payload = {
                "logdir": common.first_value(metrics),
                "mbean": ",".join(metrics.keys()),
                "function": "localstat",
                "localbrk": thisqm,
                "server": thisqm,
                "port": values.get("port", "9092"),
                "jmxport": values.get("jmxport", "9999"),
                "security": values.get("security", "PLAINTEXT"),
            }
            if values.get("username"):
                java_arg_payload["username"] = values.get("username")
            if values.get("pwd"):
                java_arg_payload["pwd"] = values.get("pwd")
            if values.get("sasl_mechanism"):
                java_arg_payload["sasl_mechanism"] = values.get("sasl_mechanism")

            common.run_command(
                [
                    "java",
                    "-cp",
                    "/midleolibs/libs/*:" + jar_path,
                    "midleo_kafka.kafka_main",
                    json.dumps(java_arg_payload),
                ],
                "kafka",
            )

        if common.optadvisor_collection_enabled(optadvisor_config):
            _collect_optadvisor(thisqm, optadvisor_config, values, jar_path)

    except (json.JSONDecodeError, TypeError, ValueError) as err:
        classes.Err("Error in kafka statistics:" + str(err))


def resetStat(thisnode, website, webssl, inttoken, stat_data):
    _, legacy_stat_data = common.split_optadvisor_config(stat_data if isinstance(stat_data, dict) else {}, KAFKA_CONFIG_KEYS)
    common.post_csv_stats(
        "kafka",
        "kafka",
        website,
        webssl,
        inttoken,
        legacy_stat_data,
        lambda logdir, subtype: logdir + "Statistics_" + subtype + ".csv",
    )
    common.flush_optadvisor_telemetry("kafka", thisnode, website, webssl, inttoken, stat_data, KAFKA_CONFIG_KEYS)
