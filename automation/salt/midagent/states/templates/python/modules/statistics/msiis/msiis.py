import base64
import csv
import hashlib
import json
import os

try:
    from Crypto.Hash import MD4
except Exception:
    MD4 = None
try:
    import winrm
except Exception:
    winrm = None

from modules.base import classes
from modules.statistics import common
from modules.statistics.msiis.modules import srvinfo

_original_hashlib_new = hashlib.new


def md4_patched(name, data=b''):
    if name == 'md4':
        if MD4 is None:
            return _original_hashlib_new(name, data)
        h = MD4.new()
        h.update(data)
        return h
    return _original_hashlib_new(name, data)


hashlib.new = md4_patched


def _decode_password(value):
    if not value:
        return ""
    padded = value + "=" * (4 - len(value) % 4)
    return base64.b64decode(padded).decode("utf-8")


OPTADVISOR_COLLECTOR_NAME = "msiis-winrm-collector"
OPTADVISOR_TECHNOLOGY = "msiis"


def _resource(resource_type, technical_key, name, status="unknown", metadata=None, metrics=None):
    return {
        "resource_type": resource_type,
        "technical_key": common.safe_text(technical_key),
        "name": common.safe_text(name or technical_key),
        "status": common.safe_text(status or "unknown"),
        "metadata": metadata or {},
        "metrics": metrics or [],
    }


def _parse_winrm_json(output):
    try:
        parsed = json.loads(output or "[]")
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
    if isinstance(parsed, dict):
        return [parsed]
    return parsed if isinstance(parsed, list) else []


def _run_json_ps(session, script, thisnode):
    result = session.run_ps(script.format(serverName=thisnode))
    output = result.std_out.decode('utf-8', errors='ignore')
    return _parse_winrm_json(output)


def _status_from_value(value):
    number = common.numeric_value(value)
    if number == 1:
        return "started"
    if number == 0:
        return "stopped"
    return "unknown"


def buildOptAdvisorPayload(thisnode, config, app_pool_rows=None, perf_rows=None, collected_at=None):
    resources = []
    target = {"status": "running"}

    pools = {}
    for row in app_pool_rows or []:
        if not isinstance(row, dict):
            continue
        pool = common.safe_text(row.get("pool"))
        if not pool:
            continue
        pools.setdefault(pool, {"metrics": [], "status": "unknown"})
        metric_name = common.safe_text(row.get("metric"))
        if metric_name == "AppPoolState":
            status = _status_from_value(row.get("value"))
            pools[pool]["status"] = status
            common.add_metric(pools[pool]["metrics"], common.metric_string("app_pool_status", status))

    for pool, data in pools.items():
        if data["metrics"]:
            resources.append(_resource("msiis_app_pool", str(thisnode) + "/app_pool/" + pool, pool, data["status"], {}, data["metrics"]))

    perf_by_instance = {}
    metric_map = {
        "Total Requests Served": "request_count",
        "Health Ping Reply Latency": "health_ping_latency_ms",
        "Active Listener Channels": "active_listener_channels",
        "Total WAS Messages Received": "messages_received",
    }
    for row in perf_rows or []:
        if not isinstance(row, dict):
            continue
        instance = common.safe_text(row.get("instance") or row.get("server") or "default")
        metric_name = common.safe_text(row.get("metric"))
        mapped = metric_map.get(metric_name)
        if not mapped:
            continue
        perf_by_instance.setdefault(instance, [])
        common.add_metric(perf_by_instance[instance], common.metric_number(mapped, row.get("value")))

    for instance, metrics in perf_by_instance.items():
        if metrics:
            resources.append(_resource("msiis_worker_process", str(thisnode) + "/worker/" + instance, instance, "running", {}, metrics))

    return common.build_optadvisor_payload(
        "msiis",
        OPTADVISOR_TECHNOLOGY,
        OPTADVISOR_COLLECTOR_NAME,
        thisnode,
        config,
        target,
        resources,
        collected_at,
    )


def _collect_optadvisor(thisnode, config, session, functions):
    app_pool_rows = []
    perf_rows = []
    if functions.get("AppPoolState"):
        app_pool_rows = _run_json_ps(session, functions["AppPoolState"], thisnode)
    if functions.get("PerfMetrics"):
        perf_rows = _run_json_ps(session, functions["PerfMetrics"], thisnode)
    payload = buildOptAdvisorPayload(thisnode, config, app_pool_rows, perf_rows, common.utc_now())
    if payload is not None:
        common.append_optadvisor_payload("msiis", thisnode, payload)


def getStat(thisqm, inpdata):
    try:
        if winrm is None:
            raise RuntimeError("python winrm module is not available")
        inpdata = common.parse_json_object(inpdata)
        values, metrics = common.pop_fields(
            inpdata, {"usr": "", "pwd": "", "mngmport": "", "ssl": ""}
        )
        optadvisor_config, metrics = common.split_optadvisor_config(metrics)

        scheme = "https" if values["ssl"] else "http"
        session_url = scheme + "://" + str(thisqm) + ":" + str(values["mngmport"]) + "/wsman"
        session = winrm.Session(
            session_url,
            auth=(values["usr"], _decode_password(values["pwd"])),
            transport='ntlm',
            server_cert_validation=os.environ.get("MIDLEO_WINRM_CERT_VALIDATION", "ignore"),
            operation_timeout_sec=10,
            read_timeout_sec=20,
        )
        functions = srvinfo.SRVFUNC() if hasattr(srvinfo, 'SRVFUNC') else {}

        for key, logdir in metrics.items():
            ps_script = functions.get(key)
            if not ps_script:
                continue

            result = session.run_ps(ps_script.format(serverName=thisqm))
            output = result.std_out.decode('utf-8', errors='ignore')
            json_data = json.loads(output)
            if not isinstance(json_data, list) or not json_data:
                continue

            filename = os.path.join(logdir, "Statistics_" + key + ".csv")
            file_exists = os.path.isfile(filename)
            with open(filename, mode='a', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=json_data[0].keys())
                if not file_exists:
                    writer.writeheader()
                writer.writerows(json_data)

        if common.optadvisor_collection_enabled(optadvisor_config):
            _collect_optadvisor(thisqm, optadvisor_config, session, functions)

    except Exception as err:
        classes.Err("Error in msiis statistics:" + str(err))


def resetStat(thisnode, website, webssl, inttoken, stat_data):
    _, legacy_stat_data = common.split_optadvisor_config(stat_data if isinstance(stat_data, dict) else {})
    common.post_csv_stats(
        "msiis",
        "msiis",
        website,
        webssl,
        inttoken,
        legacy_stat_data,
        lambda logdir, subtype: logdir + "Statistics_" + subtype + ".csv",
    )
    common.flush_optadvisor_telemetry("msiis", thisnode, website, webssl, inttoken, stat_data)
