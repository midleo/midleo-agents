import base64
import json
from urllib.parse import quote

import requests
import urllib3

from modules.base import classes
from modules.statistics import common


OPTADVISOR_COLLECTOR_NAME = "rabbitmq-management-collector"
OPTADVISOR_TECHNOLOGY = "rabbitmq"
RABBITMQ_CONFIG_KEYS = {"usr", "pwd", "mngmport", "port", "ssl", "sslverify", "ssl_verify", "vhost"}


def _decode_password(value):
    if not value:
        return ""
    try:
        padded = value + "=" * ((4 - len(value) % 4) % 4)
        return base64.b64decode(padded).decode("utf-8")
    except Exception:
        return value


def _resource(resource_type, technical_key, name, status="unknown", metadata=None, metrics=None):
    return {
        "resource_type": resource_type,
        "technical_key": common.safe_text(technical_key),
        "name": common.safe_text(name or technical_key),
        "status": common.safe_text(status or "unknown"),
        "metadata": metadata or {},
        "metrics": metrics or [],
    }


def _rate(row, *path):
    value = common.nested(row, *path)
    return value


def buildOptAdvisorPayload(thisnode, config, nodes=None, queues=None, exchanges=None, connections=None, channels=None, collected_at=None):
    resources = []
    target = {"status": "running"}

    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        name = common.safe_text(node.get("name"))
        if not name:
            continue
        status = "running" if node.get("running") is True else "stopped"
        metrics = []
        common.add_metric(metrics, common.metric_number("memory_used_bytes", node.get("mem_used")))
        common.add_metric(metrics, common.metric_number("disk_free_bytes", node.get("disk_free")))
        common.add_metric(metrics, common.metric_number("fd_used", node.get("fd_used")))
        common.add_metric(metrics, common.metric_number("sockets_used", node.get("sockets_used")))
        if metrics:
            resources.append(_resource("rabbitmq_node", name, name, status, {}, metrics))

    for queue in queues or []:
        if not isinstance(queue, dict):
            continue
        name = common.safe_text(queue.get("name"))
        vhost = common.safe_text(queue.get("vhost"))
        if not name:
            continue
        technical_key = (vhost + "/" if vhost else "") + name
        metrics = []
        common.add_metric(metrics, common.metric_number("messages_ready", queue.get("messages_ready")))
        common.add_metric(metrics, common.metric_number("messages_unacknowledged", queue.get("messages_unacknowledged")))
        common.add_metric(metrics, common.metric_number("consumers", queue.get("consumers")))
        common.add_metric(metrics, common.metric_number("publish_rate", _rate(queue, "message_stats", "publish_details", "rate")))
        common.add_metric(metrics, common.metric_number("deliver_get_rate", _rate(queue, "message_stats", "deliver_get_details", "rate")))
        if metrics:
            resources.append(_resource("rabbitmq_queue", technical_key, name, common.safe_text(queue.get("state")) or "running", {"vhost": vhost}, metrics))

    if isinstance(connections, list):
        resources.append(_resource("rabbitmq_connection", str(thisnode) + "/connections", "Connections", "running", {}, [common.metric_number("connection_count", len(connections))]))

    if isinstance(channels, list):
        resources.append(_resource("rabbitmq_channel", str(thisnode) + "/channels", "Channels", "running", {}, [common.metric_number("channel_count", len(channels))]))

    for exchange in exchanges or []:
        if not isinstance(exchange, dict):
            continue
        name = common.safe_text(exchange.get("name"))
        vhost = common.safe_text(exchange.get("vhost"))
        if not name or name.startswith("amq.") or name == "":
            continue
        technical_key = (vhost + "/" if vhost else "") + name
        metrics = []
        common.add_metric(metrics, common.metric_number("publish_in_rate", _rate(exchange, "message_stats", "publish_in_details", "rate")))
        common.add_metric(metrics, common.metric_number("publish_out_rate", _rate(exchange, "message_stats", "publish_out_details", "rate")))
        if metrics:
            resources.append(_resource("rabbitmq_exchange", technical_key, name, "running", {"vhost": vhost, "type": common.safe_text(exchange.get("type"))}, metrics))

    return common.build_optadvisor_payload(
        "rabbitmq",
        OPTADVISOR_TECHNOLOGY,
        OPTADVISOR_COLLECTOR_NAME,
        thisnode,
        config,
        target,
        resources,
        collected_at,
    )


def _request_json(base_url, path, auth, verify):
    try:
        if not verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        res = requests.get(
            base_url.rstrip("/") + path,
            auth=auth,
            timeout=common.DEFAULT_TIMEOUT_SECONDS,
            verify=verify,
            headers={"Accept": "application/json"},
        )
        if res.status_code >= 200 and res.status_code < 300:
            return res.json()
        classes.Err("rabbitmq optadvisor HTTPResponse:" + str(res.status_code))
    except Exception as err:
        classes.Err("rabbitmq optadvisor request error:" + str(err))
    return []


def _collect_optadvisor(thisnode, config, values):
    scheme = "https" if common.truthy(values.get("ssl")) else "http"
    port = values.get("mngmport") or values.get("port") or "15672"
    base_url = scheme + "://" + str(thisnode) + ":" + str(port) + "/api"
    auth = (values.get("usr", ""), _decode_password(values.get("pwd", "")))
    verify = common.truthy(values.get("ssl_verify") or values.get("sslverify") or "yes")
    vhost = common.safe_text(values.get("vhost"))
    queue_path = "/queues/" + quote(vhost, safe="") if vhost else "/queues"
    exchange_path = "/exchanges/" + quote(vhost, safe="") if vhost else "/exchanges"

    nodes = _request_json(base_url, "/nodes", auth, verify)
    queues = _request_json(base_url, queue_path, auth, verify)
    exchanges = _request_json(base_url, exchange_path, auth, verify)
    connections = _request_json(base_url, "/connections", auth, verify)
    channels = _request_json(base_url, "/channels", auth, verify)
    payload = buildOptAdvisorPayload(thisnode, config, nodes, queues, exchanges, connections, channels, common.utc_now())
    if payload is not None:
        common.append_optadvisor_payload("rabbitmq", thisnode, payload)


def getStat(thisqm, inpdata):
    try:
        inpdata = common.parse_json_object(inpdata)
        values, metrics = common.pop_fields(
            inpdata,
            {"usr": "", "pwd": "", "mngmport": "15672", "port": "", "ssl": "no", "sslverify": "", "ssl_verify": "", "vhost": ""},
        )
        optadvisor_config, _ = common.split_optadvisor_config(metrics, RABBITMQ_CONFIG_KEYS)
        if common.optadvisor_collection_enabled(optadvisor_config):
            _collect_optadvisor(thisqm, optadvisor_config, values)
    except (json.JSONDecodeError, TypeError, ValueError) as err:
        classes.Err("Error in rabbitmq statistics:" + str(err))


def resetStat(thisnode, website, webssl, _legacy_token, stat_data):
    common.flush_optadvisor_telemetry("rabbitmq", thisnode, website, webssl, _legacy_token, stat_data, RABBITMQ_CONFIG_KEYS)
