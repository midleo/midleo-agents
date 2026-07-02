import json, glob, os, csv, socket, uuid, fnmatch, time
from modules.base import classes, file_utils, makerequest
from modules.statistics import common
from datetime import datetime, timezone

try:
    import pymqi
    MQ_ERROR = pymqi.MQMIError
    PYMQI_IMPORT_ERROR = None
except ImportError as ex:
    pymqi = None
    MQ_ERROR = Exception
    PYMQI_IMPORT_ERROR = ex


OPTADVISOR_SCHEMA_VERSION = "1.0"
OPTADVISOR_COLLECTOR_NAME = "mq-pymqi-collector"
OPTADVISOR_COLLECTOR_VERSION = "1.0.0"
OPTADVISOR_TECHNOLOGY = "ibmmq"
OPTADVISOR_COLLECTION_MODES = {
    "summary_only",
    "summary_plus_topn",
    "include_list",
    "deep_scan",
}
OPTADVISOR_DEFAULTS = {
    "collection_mode": "summary_plus_topn",
    "top_n_depth": 25,
    "top_n_age": 25,
    "max_queue_details_per_run": 100,
    "depth_percent_threshold": 70,
    "oldest_age_threshold_seconds": 1800,
    "include_patterns": [],
    "exclude_patterns": ["SYSTEM.*", "AMQ.*", "MQAI.*"],
    "deep_scan_interval_hours": 24,
    "collect_system_queues": False,
}


def qmConn(thisqm):
    if pymqi is None:
        classes.Err("Exception:pymqi is not available:" + str(PYMQI_IMPORT_ERROR))
        return None
    try:
        qmgr = pymqi.connect(thisqm)
    except MQ_ERROR as ex:
        classes.Err("Exception:" + str(ex))
        qmgr = None
    return qmgr


def qmDisc(thisqm):
    if thisqm is not None:
        thisqm.disconnect()


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


def _int_config(inpdata, key, default, min_value=0, max_value=1000000):
    try:
        value = int(inpdata.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(min_value, min(value, max_value))


def _parse_patterns(value):
    if isinstance(value, list):
        values = value
    elif isinstance(value, str):
        values = value.split(",")
    else:
        values = []
    return [_safe_text(item) for item in values if _safe_text(item)]


def _optadvisor_mq_config(inpdata):
    cfg = {}
    mode = _safe_text(inpdata.get("collection_mode") or inpdata.get("optadvisor_collection_mode")).lower()
    if mode not in OPTADVISOR_COLLECTION_MODES:
        mode = OPTADVISOR_DEFAULTS["collection_mode"]
    cfg["collection_mode"] = mode
    cfg["top_n_depth"] = _int_config(inpdata, "top_n_depth", OPTADVISOR_DEFAULTS["top_n_depth"], 0, 250)
    cfg["top_n_age"] = _int_config(inpdata, "top_n_age", OPTADVISOR_DEFAULTS["top_n_age"], 0, 250)
    cfg["max_queue_details_per_run"] = _int_config(
        inpdata,
        "max_queue_details_per_run",
        OPTADVISOR_DEFAULTS["max_queue_details_per_run"],
        1,
        240,
    )
    cfg["depth_percent_threshold"] = _int_config(
        inpdata,
        "depth_percent_threshold",
        OPTADVISOR_DEFAULTS["depth_percent_threshold"],
        0,
        100,
    )
    cfg["oldest_age_threshold_seconds"] = _int_config(
        inpdata,
        "oldest_age_threshold_seconds",
        OPTADVISOR_DEFAULTS["oldest_age_threshold_seconds"],
        0,
        86400 * 30,
    )
    cfg["include_patterns"] = _parse_patterns(inpdata.get("include_patterns", OPTADVISOR_DEFAULTS["include_patterns"]))
    cfg["collect_system_queues"] = _truthy(inpdata.get("collect_system_queues"))
    raw_exclude_patterns = inpdata.get("exclude_patterns", None)
    if raw_exclude_patterns is None and cfg["collect_system_queues"]:
        cfg["exclude_patterns"] = []
    else:
        cfg["exclude_patterns"] = _parse_patterns(raw_exclude_patterns if raw_exclude_patterns is not None else OPTADVISOR_DEFAULTS["exclude_patterns"])
    if not cfg["exclude_patterns"] and not cfg["collect_system_queues"]:
        cfg["exclude_patterns"] = list(OPTADVISOR_DEFAULTS["exclude_patterns"])
    cfg["deep_scan_interval_hours"] = _int_config(
        inpdata,
        "deep_scan_interval_hours",
        OPTADVISOR_DEFAULTS["deep_scan_interval_hours"],
        1,
        24 * 31,
    )
    cfg["force_deep_scan"] = _truthy(
        inpdata.get("force_deep_scan")
        or inpdata.get("deep_scan_requested")
        or inpdata.get("manual_deep_scan")
    )
    return cfg


def _optadvisor_enabled(inpdata):
    return _truthy(
        inpdata.get("optadvisor")
        or inpdata.get("optadvisor_enabled")
        or inpdata.get("optimization_advisor")
    )


def _safe_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip().replace("\u0000", "")
    return str(value).strip().replace("\u0000", "")


def _pcf_get(row, parameter, default=None):
    if parameter is None:
        return default
    try:
        return row[parameter]
    except Exception:
        return default


def _number_metric(key, value):
    if value is None:
        return None
    try:
        return {"key": key, "value": float(value), "value_type": "number"}
    except (TypeError, ValueError):
        return None


def _string_metric(key, value):
    value = _safe_text(value)
    if not value:
        return None
    return {"key": key, "value": value, "value_type": "string"}


def _boolean_metric(key, value):
    if value is None:
        return None
    if isinstance(value, bool):
        bool_value = value
    else:
        try:
            bool_value = int(value) != 0
        except (TypeError, ValueError):
            bool_value = _truthy(value)
    return {"key": key, "value": bool_value, "value_type": "boolean"}


def _add_metric(metrics, metric):
    if metric is not None:
        metrics.append(metric)


def _optadvisor_log_path(thisqm):
    return os.path.join(os.getcwd(), "logs", "ibmmq_" + str(thisqm) + "_optadvisor.jsonl")


def _optadvisor_state_path(thisqm):
    return os.path.join(os.getcwd(), "logs", "ibmmq_" + str(thisqm) + "_optadvisor_state.json")


def _append_optadvisor_payload(thisqm, payload):
    os.makedirs(os.path.join(os.getcwd(), "logs"), exist_ok=True)
    with open(_optadvisor_log_path(thisqm), "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n")


def _read_optadvisor_state(thisqm):
    path = _optadvisor_state_path(thisqm)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_optadvisor_state(thisqm, data):
    try:
        os.makedirs(os.path.join(os.getcwd(), "logs"), exist_ok=True)
        with open(_optadvisor_state_path(thisqm), "w", encoding="utf-8") as f:
            json.dump(data if isinstance(data, dict) else {}, f, separators=(",", ":"), sort_keys=True)
    except Exception as ex:
        classes.Err("ibmmq optadvisor state write error:" + str(ex))


def _parse_iso_epoch(value):
    try:
        text = _safe_text(value).replace("Z", "+00:00")
        if not text:
            return 0
        return datetime.fromisoformat(text).timestamp()
    except Exception:
        return 0


def _deep_scan_allowed(thisqm, cfg):
    if cfg.get("collection_mode") != "deep_scan":
        return False, ""
    state = _read_optadvisor_state(thisqm)
    last = _safe_text(state.get("last_deep_scan_at"))
    if cfg.get("force_deep_scan"):
        return True, last
    last_epoch = _parse_iso_epoch(last)
    if last_epoch <= 0:
        return True, last
    interval_seconds = int(cfg.get("deep_scan_interval_hours") or 24) * 3600
    return (time.time() - last_epoch) >= interval_seconds, last


def _get_server_id(inpdata, thisqm):
    return (
        inpdata.get("server_id")
        or inpdata.get("appsrvid")
        or inpdata.get("serverid")
        or inpdata.get("srvid")
        or inpdata.get("qmid")
        or thisqm
    )


def qMgrInfo(thisqm):
    info = {"status": "running"}
    try:
        pcf = pymqi.PCFExecute(thisqm, response_wait_interval=5000)
        response = pcf.MQCMD_INQUIRE_Q_MGR([], [])
        for qmgr_info in response:
            dlq = _safe_text(
                _pcf_get(qmgr_info, getattr(pymqi.CMQC, "MQCA_DEAD_LETTER_Q_NAME", None))
            )
            command_level = _pcf_get(qmgr_info, getattr(pymqi.CMQC, "MQIA_COMMAND_LEVEL", None))
            if dlq:
                info["dead_letter_queue"] = dlq
            if command_level is not None:
                info["command_level"] = command_level
            break
    except MQ_ERROR as ex:
        classes.Err("ibmmq qmgr info error:" + str(ex))
    except Exception as ex:
        classes.Err("ibmmq qmgr info error:" + str(ex))
    return info


def qStat(thisqm, q, queues):
    try:
        args = []
        args.append(
            pymqi.CFST(Parameter=pymqi.CMQC.MQCA_Q_NAME, String=q.encode("utf-8"))
        )
        args.append(
            pymqi.CFIN(Parameter=pymqi.CMQC.MQIA_Q_TYPE, Value=pymqi.CMQC.MQQT_LOCAL)
        )

        filters = []

        pcf = pymqi.PCFExecute(thisqm, response_wait_interval=5000)
        response = pcf.MQCMD_INQUIRE_Q(args, filters)
        for queue_info in response:
            now = datetime.now().replace(microsecond=0)
            qname = queue_info[pymqi.CMQC.MQCA_Q_NAME].decode("utf-8").strip()
            if qname:
                queues[qname] = {}
                queues[qname]["name"] = qname
                queues[qname]["now"] = now.timestamp()
                queues[qname]["curdepth"] = queue_info[pymqi.CMQC.MQIA_CURRENT_Q_DEPTH]
                queues[qname]["maxdepth"] = queue_info[pymqi.CMQC.MQIA_MAX_Q_DEPTH]
                queues[qname]["percfull"] = depthperc(queue_info)
                queues[qname]["qtype"] = "local"
                usage = _pcf_get(queue_info, getattr(pymqi.CMQC, "MQIA_USAGE", None))
                if usage is not None:
                    queues[qname]["usage"] = usage
                    if usage == getattr(pymqi.CMQC, "MQUS_TRANSMISSION", -999):
                        queues[qname]["qtype"] = "transmission"
                queues[qname]["backthres"] = queue_info[
                    pymqi.CMQC.MQIA_BACKOUT_THRESHOLD
                ]
                queues[qname]["trdepth"] = queue_info[pymqi.CMQC.MQIA_TRIGGER_DEPTH]
                queues[qname]["maxmsgl"] = queue_info[pymqi.CMQC.MQIA_MAX_MSG_LENGTH]
                queues[qname]["depthhlim"] = queue_info[
                    pymqi.CMQC.MQIA_Q_DEPTH_HIGH_LIMIT
                ]
                queues[qname]["depthllim"] = queue_info[
                    pymqi.CMQC.MQIA_Q_DEPTH_LOW_LIMIT
                ]
                inhibit_get = _pcf_get(queue_info, getattr(pymqi.CMQC, "MQIA_INHIBIT_GET", None))
                inhibit_put = _pcf_get(queue_info, getattr(pymqi.CMQC, "MQIA_INHIBIT_PUT", None))
                if inhibit_get is not None:
                    queues[qname]["inhibit_get"] = inhibit_get
                if inhibit_put is not None:
                    queues[qname]["inhibit_put"] = inhibit_put
    except MQ_ERROR as ex:
        classes.Err("Exception:" + str(ex))
    return queues


def qStatInfo(thisqm, q, queues, include_empty=False):
    try:
        args = []
        args.append(
            pymqi.CFST(Parameter=pymqi.CMQC.MQCA_Q_NAME, String=q.encode("utf-8"))
        )
        args.append(
            pymqi.CFIN(Parameter=pymqi.CMQC.MQIA_Q_TYPE, Value=pymqi.CMQC.MQQT_LOCAL)
        )
        args.append(
            pymqi.CFIN(
                Parameter=pymqi.CMQCFC.MQIACF_Q_STATUS_ATTRS,
                Value=pymqi.CMQCFC.MQIACF_ALL,
            )
        )
        filters = []
        if not include_empty:
            filters.append(
                pymqi.CFIF(
                    Parameter=pymqi.CMQC.MQIA_CURRENT_Q_DEPTH,
                    Operator=pymqi.CMQCFC.MQCFOP_GREATER,
                    FilterValue=0,
                )
            )

        pcf = pymqi.PCFExecute(thisqm, response_wait_interval=5000)
        response = pcf.MQCMD_INQUIRE_Q_STATUS(args, filters)
        for queue_info in response:

            qname = queue_info[pymqi.CMQC.MQCA_Q_NAME].decode("utf-8").strip()
            if qname not in queues:
                queues[qname] = {}
            if qname:
                op_in = _pcf_get(queue_info, pymqi.CMQC.MQIA_OPEN_INPUT_COUNT)
                op_out = _pcf_get(queue_info, pymqi.CMQC.MQIA_OPEN_OUTPUT_COUNT)
                uncommitted = _pcf_get(queue_info, pymqi.CMQCFC.MQIACF_UNCOMMITTED_MSGS)
                oldest = _pcf_get(queue_info, pymqi.CMQCFC.MQIACF_OLDEST_MSG_AGE)
                if op_in is not None:
                    queues[qname]["opincount"] = op_in
                if op_out is not None:
                    queues[qname]["opoutcount"] = op_out
                if uncommitted is not None:
                    queues[qname]["uncmess"] = uncommitted
                if oldest is not None:
                    queues[qname]["oldmessage"] = oldest
                last_get_date = _safe_text(_pcf_get(queue_info, pymqi.CMQCFC.MQCACF_LAST_GET_DATE))
                last_get_time = _safe_text(_pcf_get(queue_info, pymqi.CMQCFC.MQCACF_LAST_GET_TIME))
                last_put_date = _safe_text(_pcf_get(queue_info, pymqi.CMQCFC.MQCACF_LAST_PUT_DATE))
                last_put_time = _safe_text(_pcf_get(queue_info, pymqi.CMQCFC.MQCACF_LAST_PUT_TIME))
                if last_get_date or last_get_time:
                    queues[qname]["lastget"] = (last_get_date + " " + last_get_time).strip()
                if last_put_date or last_put_time:
                    queues[qname]["lastput"] = (last_put_date + " " + last_put_time).strip()
    except MQ_ERROR as ex:
        classes.Err("Exception:" + str(ex))
    except Exception as ex:
        classes.Err("Exception:" + str(ex))
    return queues


def qResStat(thisqm, q, queues):
    try:
        args = []
        args.append(
            pymqi.CFST(Parameter=pymqi.CMQC.MQCA_Q_NAME, String=q.encode("utf-8"))
        )
        filters = []
        pcf = pymqi.PCFExecute(thisqm, response_wait_interval=5000)
        response = pcf.MQCMD_RESET_Q_STATS(args, filters)
        for queue_info in response:
            qname = queue_info[pymqi.CMQC.MQCA_Q_NAME].decode("utf-8").strip()
            if qname and qname not in queues:
                queues[qname] = {}
            if qname:
                queues[qname]["highqdepth"] = queue_info[pymqi.CMQC.MQIA_HIGH_Q_DEPTH]
                queues[qname]["deqcount"] = queue_info[pymqi.CMQC.MQIA_MSG_DEQ_COUNT]
                queues[qname]["enqcount"] = queue_info[pymqi.CMQC.MQIA_MSG_ENQ_COUNT]
                queues[qname]["timereset"] = queue_info[
                    pymqi.CMQC.MQIA_TIME_SINCE_RESET
                ]
    except MQ_ERROR as ex:
        classes.Err("Exception:" + str(ex))
    return queues


def chStat(thisqm, ch, chls):
    try:
        args = []
        args.append(
            pymqi.CFST(
                Parameter=pymqi.CMQCFC.MQCACH_CHANNEL_NAME, String=ch.encode("utf-8")
            )
        )
        args.append(
            pymqi.CFIL(
                Parameter=pymqi.CMQCFC.MQIACH_CHANNEL_INSTANCE_ATTRS,
                Values=[
                    pymqi.CMQCFC.MQCACH_CHANNEL_NAME,
                    pymqi.CMQCFC.MQCACH_CONNECTION_NAME,
                    pymqi.CMQCFC.MQIACH_MSGS,
                    pymqi.CMQCFC.MQIACH_CHANNEL_STATUS,
                    pymqi.CMQCFC.MQIACH_BYTES_SENT,
                    pymqi.CMQCFC.MQIACH_BYTES_RECEIVED,
                    pymqi.CMQCFC.MQIACH_BUFFERS_SENT,
                    pymqi.CMQCFC.MQIACH_BUFFERS_RECEIVED,
                    pymqi.CMQCFC.MQIACH_INDOUBT_STATUS,
                    pymqi.CMQCFC.MQIACH_CHANNEL_SUBSTATE,
                    pymqi.CMQCFC.MQCACH_CHANNEL_START_DATE,
                    pymqi.CMQCFC.MQIACH_CURRENT_MSGS,
                    pymqi.CMQCFC.MQCACH_CHANNEL_START_TIME,
                ],
            )
        )

        filters = []
        pcf = pymqi.PCFExecute(thisqm, response_wait_interval=5000)
        response = pcf.MQCMD_INQUIRE_CHANNEL_STATUS(args, filters)
        for chl_info in response:
            now = datetime.now().replace(microsecond=0)
            chlname = chl_info[pymqi.CMQCFC.MQCACH_CHANNEL_NAME].decode("utf-8").strip()
            if chlname:
                chls[chlname] = {}
                chls[chlname]["name"] = chlname
                chls[chlname]["now"] = now.timestamp()
                chls[chlname]["conname"] = (
                    chl_info[pymqi.CMQCFC.MQCACH_CONNECTION_NAME]
                    .decode("utf-8")
                    .strip()
                    .replace("\u0000", "")
                )
                chls[chlname]["status"] = chl_st()[
                    chl_info[pymqi.CMQCFC.MQIACH_CHANNEL_STATUS]
                ]
                chls[chlname]["msgs"] = chl_info[pymqi.CMQCFC.MQIACH_MSGS]
                chls[chlname]["current_msgs"] = chl_info[
                    pymqi.CMQCFC.MQIACH_CURRENT_MSGS
                ]
                chls[chlname]["bytes_sent"] = chl_info[pymqi.CMQCFC.MQIACH_BYTES_SENT]
                chls[chlname]["bytes_received"] = chl_info[pymqi.CMQCFC.MQIACH_BYTES_RECEIVED]
                chls[chlname]["buff_sent"] = chl_info[pymqi.CMQCFC.MQIACH_BUFFERS_SENT]
                chls[chlname]["buff_received"] = _pcf_get(
                    chl_info,
                    getattr(pymqi.CMQCFC, "MQIACH_BUFFERS_RCVD", getattr(pymqi.CMQCFC, "MQIACH_BUFFERS_RECEIVED", None)),
                )
                chls[chlname]["indoubt_status"] = _pcf_get(
                    chl_info,
                    pymqi.CMQCFC.MQIACH_INDOUBT_STATUS,
                )
    except MQ_ERROR as ex:
        classes.Err("Exception:" + str(ex))
    except Exception as ex:
        classes.Err("Exception:" + str(ex))
    return chls


def chl_st():
    return {
        pymqi.CMQCFC.MQCHS_INACTIVE: "inactive",
        pymqi.CMQCFC.MQCHS_BINDING: "binding",
        pymqi.CMQCFC.MQCHS_RETRYING: "retrying",
        pymqi.CMQCFC.MQCHS_STARTING: "starting",
        pymqi.CMQCFC.MQCHS_RUNNING: "running",
        pymqi.CMQCFC.MQCHS_STOPPING: "stopping",
        pymqi.CMQCFC.MQCHS_STOPPED: "stopped",
        pymqi.CMQCFC.MQCHS_REQUESTING: "requesting",
        pymqi.CMQCFC.MQCHS_PAUSED: "paused",
        pymqi.CMQCFC.MQCHS_INITIALIZING: "initializing",
    }


def listener_st():
    cmqcfc = pymqi.CMQCFC
    return {
        getattr(cmqcfc, "MQSVC_STATUS_STOPPED", -1): "stopped",
        getattr(cmqcfc, "MQSVC_STATUS_STARTING", -1): "starting",
        getattr(cmqcfc, "MQSVC_STATUS_RUNNING", -1): "running",
        getattr(cmqcfc, "MQSVC_STATUS_STOPPING", -1): "stopping",
        getattr(cmqcfc, "MQSVC_STATUS_RETRYING", -1): "retrying",
    }


def listenerStat(thisqm, listener_name, listeners):
    name_param = getattr(pymqi.CMQCFC, "MQCACH_LISTENER_NAME", None)
    status_param = getattr(pymqi.CMQCFC, "MQIACH_LISTENER_STATUS", None)
    if name_param is None or status_param is None:
        classes.Err("ibmmq listener status constants unavailable")
        return listeners

    try:
        args = [
            pymqi.CFST(Parameter=name_param, String=listener_name.encode("utf-8"))
        ]
        filters = []
        pcf = pymqi.PCFExecute(thisqm, response_wait_interval=5000)
        response = pcf.MQCMD_INQUIRE_LISTENER_STATUS(args, filters)
        status_map = listener_st()
        for listener_info in response:
            lname = _safe_text(_pcf_get(listener_info, name_param))
            if not lname:
                continue
            status_value = _pcf_get(listener_info, status_param)
            listeners[lname] = {
                "name": lname,
                "status": status_map.get(status_value, _safe_text(status_value)),
            }
    except MQ_ERROR as ex:
        classes.Err("ibmmq listener status error:" + str(ex))
    except Exception as ex:
        classes.Err("ibmmq listener status error:" + str(ex))
    return listeners


def _is_system_queue(qname):
    upper = _safe_text(qname).upper()
    return upper.startswith("SYSTEM.") or upper.startswith("AMQ.") or upper.startswith("MQAI.")


def _matches_any(name, patterns):
    qname = _safe_text(name)
    return any(fnmatch.fnmatchcase(qname.upper(), _safe_text(pattern).upper()) for pattern in patterns)


def _depth_value(qdata):
    try:
        return float(qdata.get("curdepth") or 0)
    except (TypeError, ValueError):
        return 0.0


def _age_value(qdata):
    try:
        return float(qdata.get("oldmessage") or 0)
    except (TypeError, ValueError):
        return 0.0


def _open_input(qdata):
    try:
        return int(qdata.get("opincount") or 0)
    except (TypeError, ValueError):
        return 0


def _open_output(qdata):
    try:
        return int(qdata.get("opoutcount") or 0)
    except (TypeError, ValueError):
        return 0


def _depth_percent(qdata):
    try:
        return float(qdata.get("percfull") or 0)
    except (TypeError, ValueError):
        return 0.0


def _selection_reason_counts(selected):
    counts = {}
    for qdata in selected.values():
        for reason in qdata.get("_selection_reasons", []):
            counts[reason] = counts.get(reason, 0) + 1
    return ",".join(key + "=" + str(counts[key]) for key in sorted(counts))


def _queue_type(qdata):
    text = _safe_text(qdata.get("qtype"))
    return text if text else "local"


def _select_detail_queues(thisqm, queues, qmgr_info, cfg):
    mode = cfg["collection_mode"]
    selected = {}
    details_allowed = mode in ("summary_plus_topn", "include_list", "deep_scan")
    deep_allowed, last_deep_scan = _deep_scan_allowed(thisqm, cfg)
    effective_mode = mode
    if mode == "deep_scan" and not deep_allowed:
        details_allowed = False
        effective_mode = "summary_only"

    if not details_allowed:
        return selected, {
            "effective_mode": effective_mode,
            "last_deep_scan_at": last_deep_scan,
            "deep_scan_due": bool(deep_allowed),
        }

    details_limit = max(0, int(cfg.get("max_queue_details_per_run") or 0))
    dlq = _safe_text(qmgr_info.get("dead_letter_queue"))
    candidates = {}
    for qname, qdata in sorted((queues or {}).items()):
        qname = _safe_text(qname)
        if not qname:
            continue
        system_object = _is_system_queue(qname)
        if system_object and not cfg.get("collect_system_queues"):
            continue
        if cfg.get("exclude_patterns") and _matches_any(qname, cfg["exclude_patterns"]):
            continue
        candidates[qname] = qdata or {}

    def mark(name, reason):
        if name not in candidates:
            return
        if name not in selected:
            selected[name] = dict(candidates[name])
            selected[name]["_selection_reasons"] = []
        if reason not in selected[name]["_selection_reasons"]:
            selected[name]["_selection_reasons"].append(reason)

    if mode == "deep_scan" and deep_allowed:
        for qname in candidates:
            mark(qname, "deep_scan")

    if mode == "include_list":
        for qname in candidates:
            if _matches_any(qname, cfg.get("include_patterns", [])):
                mark(qname, "include_pattern")

    if mode == "summary_plus_topn":
        for qname in candidates:
            qdata = candidates[qname]
            if _depth_percent(qdata) >= float(cfg["depth_percent_threshold"]):
                mark(qname, "depth_percent_threshold")
            if _depth_value(qdata) > 0 and _open_input(qdata) == 0:
                mark(qname, "backlog_no_consumers")
            if _age_value(qdata) >= float(cfg["oldest_age_threshold_seconds"]):
                mark(qname, "oldest_age_threshold")
            if dlq and qname == dlq and _depth_value(qdata) > 0:
                mark(qname, "dead_letter_queue_depth")

        by_depth = sorted(candidates.items(), key=lambda item: _depth_value(item[1]), reverse=True)
        for qname, qdata in by_depth[: int(cfg["top_n_depth"] or 0)]:
            if _depth_value(qdata) > 0:
                mark(qname, "top_depth")

        by_age = sorted(candidates.items(), key=lambda item: _age_value(item[1]), reverse=True)
        for qname, qdata in by_age[: int(cfg["top_n_age"] or 0)]:
            if _age_value(qdata) > 0:
                mark(qname, "top_age")

    if details_limit and len(selected) > details_limit:
        selected = dict(sorted(
            selected.items(),
            key=lambda item: (
                _depth_percent(item[1]),
                _depth_value(item[1]),
                _age_value(item[1]),
                item[0],
            ),
            reverse=True,
        )[:details_limit])

    if mode == "deep_scan" and deep_allowed:
        state = _read_optadvisor_state(thisqm)
        state["last_deep_scan_at"] = _iso_utc()
        _write_optadvisor_state(thisqm, state)
        last_deep_scan = state["last_deep_scan_at"]

    return selected, {
        "effective_mode": effective_mode,
        "last_deep_scan_at": last_deep_scan,
        "deep_scan_due": bool(deep_allowed),
    }


def _qmgr_resource(thisqm, qmgr_info, queues, channels, listeners, selected_queues, cfg, selection_state):
    dlq = _safe_text(qmgr_info.get("dead_letter_queue"))
    app_queues = 0
    system_queues = 0
    transmission_queues = 0
    total_depth = 0.0
    max_depth_percent = 0.0
    queues_with_depth = 0
    queues_near_full = 0
    queues_with_no_consumers = 0
    queues_with_no_producers = 0
    oldest_age_max = 0.0
    dlq_depth = 0.0

    for qname, qdata in sorted((queues or {}).items()):
        qname = _safe_text(qname)
        if not qname:
            continue
        if _is_system_queue(qname):
            system_queues += 1
        else:
            app_queues += 1
        if _queue_type(qdata) == "transmission":
            transmission_queues += 1
        depth = _depth_value(qdata)
        depth_percent = _depth_percent(qdata)
        total_depth += depth
        max_depth_percent = max(max_depth_percent, depth_percent)
        if depth > 0:
            queues_with_depth += 1
            if _open_input(qdata) == 0:
                queues_with_no_consumers += 1
            if _open_output(qdata) == 0:
                queues_with_no_producers += 1
        if depth_percent >= float(cfg["depth_percent_threshold"]):
            queues_near_full += 1
        oldest_age_max = max(oldest_age_max, _age_value(qdata))
        if dlq and qname == dlq:
            dlq_depth = depth

    running_channels = sum(1 for ch in (channels or {}).values() if _safe_text(ch.get("status")).lower() == "running")
    stopped_channels = sum(1 for ch in (channels or {}).values() if _safe_text(ch.get("status")).lower() in ("stopped", "inactive", "retrying", "paused"))
    running_listeners = sum(1 for item in (listeners or {}).values() if _safe_text(item.get("status")).lower() == "running")
    stopped_listeners = sum(1 for item in (listeners or {}).values() if _safe_text(item.get("status")).lower() in ("stopped", "stopping", "retrying"))

    metrics = []
    _add_metric(metrics, _string_metric("qmgr_status", qmgr_info.get("status") or "running"))
    _add_metric(metrics, _number_metric("total_queue_count", len(queues or {})))
    _add_metric(metrics, _number_metric("local_queue_count", len(queues or {})))
    _add_metric(metrics, _number_metric("application_queue_count", app_queues))
    _add_metric(metrics, _number_metric("system_queue_count", system_queues))
    _add_metric(metrics, _number_metric("transmission_queue_count", transmission_queues))
    _add_metric(metrics, _number_metric("total_current_depth", total_depth))
    _add_metric(metrics, _number_metric("max_queue_depth_percent", max_depth_percent))
    _add_metric(metrics, _number_metric("queues_with_depth_count", queues_with_depth))
    _add_metric(metrics, _number_metric("queues_near_full_count", queues_near_full))
    _add_metric(metrics, _number_metric("queues_with_no_consumers_count", queues_with_no_consumers))
    _add_metric(metrics, _number_metric("queues_with_no_producers_count", queues_with_no_producers))
    _add_metric(metrics, _number_metric("oldest_message_age_max", oldest_age_max))
    _add_metric(metrics, _number_metric("dead_letter_queue_depth", dlq_depth))
    _add_metric(metrics, _number_metric("running_channel_count", running_channels))
    _add_metric(metrics, _number_metric("stopped_channel_count", stopped_channels))
    _add_metric(metrics, _number_metric("listener_running_count", running_listeners))
    _add_metric(metrics, _number_metric("listener_stopped_count", stopped_listeners))

    queue_details_emitted = len(selected_queues or {})
    queues_scanned = len(queues or {})
    metadata = {
        "collection_mode": cfg["collection_mode"],
        "effective_collection_mode": selection_state.get("effective_mode") or cfg["collection_mode"],
        "queue_details_emitted": queue_details_emitted,
        "queues_scanned": queues_scanned,
        "queues_suppressed": max(0, queues_scanned - queue_details_emitted),
        "selection_reason_counts": _selection_reason_counts(selected_queues or {}),
        "top_n_depth": cfg["top_n_depth"],
        "top_n_age": cfg["top_n_age"],
        "max_queue_details_per_run": cfg["max_queue_details_per_run"],
        "depth_percent_threshold": cfg["depth_percent_threshold"],
        "oldest_age_threshold_seconds": cfg["oldest_age_threshold_seconds"],
        "collect_system_queues": bool(cfg["collect_system_queues"]),
        "deep_scan_interval_hours": cfg["deep_scan_interval_hours"],
    }
    if selection_state.get("last_deep_scan_at"):
        metadata["last_deep_scan_at"] = selection_state["last_deep_scan_at"]

    return {
        "resource_type": "mq_qmgr",
        "technical_key": str(thisqm),
        "name": str(thisqm),
        "status": _safe_text(qmgr_info.get("status")) or "running",
        "parent_technical_key": None,
        "metadata": metadata,
        "metrics": metrics,
    }


def _queue_resource(qname, qdata, qmgr_info, selection_reasons=None):
    metrics = []
    _add_metric(metrics, _number_metric("current_depth", qdata.get("curdepth")))
    _add_metric(metrics, _number_metric("max_depth", qdata.get("maxdepth")))
    _add_metric(metrics, _number_metric("depth_percent", qdata.get("percfull")))
    _add_metric(metrics, _number_metric("open_input_count", qdata.get("opincount")))
    _add_metric(metrics, _number_metric("open_output_count", qdata.get("opoutcount")))
    _add_metric(metrics, _number_metric("oldest_message_age_seconds", qdata.get("oldmessage")))
    _add_metric(metrics, _boolean_metric("inhibit_get", qdata.get("inhibit_get")))
    _add_metric(metrics, _boolean_metric("inhibit_put", qdata.get("inhibit_put")))
    _add_metric(metrics, _number_metric("consumer_count", qdata.get("opincount")))
    _add_metric(metrics, _number_metric("producer_count", qdata.get("opoutcount")))

    dlq = _safe_text(qmgr_info.get("dead_letter_queue"))
    return {
        "resource_type": "mq_queue",
        "technical_key": qname,
        "name": qname,
        "status": "running",
        "parent_technical_key": None,
        "metadata": {
            "queue_type": _queue_type(qdata),
            "is_dead_letter_queue": bool(dlq and qname == dlq),
            "system_object": _is_system_queue(qname),
            "selection_reason": ",".join(selection_reasons or []),
        },
        "metrics": metrics,
    }


def _channel_resource(chname, chdata):
    metrics = []
    _add_metric(metrics, _string_metric("channel_status", chdata.get("status")))
    _add_metric(metrics, _number_metric("bytes_sent", chdata.get("bytes_sent")))
    _add_metric(metrics, _number_metric("bytes_received", chdata.get("bytes_received")))

    return {
        "resource_type": "mq_channel",
        "technical_key": chname,
        "name": chname,
        "status": _safe_text(chdata.get("status")) or None,
        "parent_technical_key": None,
        "metadata": {},
        "metrics": metrics,
    }


def _listener_resource(listener_name, listener_data):
    metrics = []
    status = _safe_text(listener_data.get("status"))
    _add_metric(metrics, _string_metric("listener_status", status))

    return {
        "resource_type": "mq_listener",
        "technical_key": listener_name,
        "name": listener_name,
        "status": status or None,
        "parent_technical_key": None,
        "metadata": {},
        "metrics": metrics,
    }


def buildOptAdvisorPayload(
    thisqm,
    inpdata,
    qmgr_info,
    queues,
    channels,
    listeners,
    collected_at=None,
):
    if not _optadvisor_enabled(inpdata):
        return None

    server_id = _safe_text(_get_server_id(inpdata, thisqm))
    if not server_id:
        classes.Err("ibmmq optadvisor disabled for missing server_id")
        return None

    mq_cfg = _optadvisor_mq_config(inpdata)
    selected_queues, selection_state = _select_detail_queues(thisqm, queues or {}, qmgr_info or {}, mq_cfg)
    resources = []
    qmgr_resource = _qmgr_resource(
        thisqm,
        qmgr_info or {"status": "running"},
        queues or {},
        channels or {},
        listeners or {},
        selected_queues,
        mq_cfg,
        selection_state,
    )
    if qmgr_resource["metrics"]:
        resources.append(qmgr_resource)

    for qname, qdata in sorted((selected_queues or {}).items()):
        resource = _queue_resource(
            _safe_text(qname),
            qdata or {},
            qmgr_info or {},
            (qdata or {}).get("_selection_reasons", []),
        )
        if resource["metrics"]:
            resources.append(resource)

    if not resources:
        return None

    qmgr_id = "".join(ch if ch.isalnum() or ch in ("_", "-", ".") else "-" for ch in str(thisqm))[:24]
    execution_id = "ibmmq-" + qmgr_id + "-" + uuid.uuid4().hex[:24]
    target = {
        "status": _safe_text((qmgr_info or {}).get("status")) or "running",
        "qmgr": str(thisqm),
    }
    if qmgr_info:
        metadata = {}
        for key in ("dead_letter_queue", "command_level"):
            if key in qmgr_info and qmgr_info[key] not in (None, ""):
                metadata[key] = qmgr_info[key]
        if metadata:
            target["metadata"] = metadata

    return {
        "schema_version": OPTADVISOR_SCHEMA_VERSION,
        "collected_at": _iso_utc(collected_at),
        "server_id": server_id,
        "technology": OPTADVISOR_TECHNOLOGY,
        "collector": {
            "name": OPTADVISOR_COLLECTOR_NAME,
            "version": str(inpdata.get("optadvisor_collector_version") or OPTADVISOR_COLLECTOR_VERSION),
            "execution_id": execution_id,
            "type": "local",
            "execution_host": socket.gethostname(),
        },
        "target": target,
        "resources": resources,
    }


def getStat(thisqm, inpdata):
    qmgr = None
    try:
        inpdata = json.loads(inpdata)

        q = inpdata.get("queues", "")
        q = [x.strip() for x in q.split(",") if x.strip()]

        chl = inpdata.get("channels", "")
        chl = [x.strip() for x in chl.split(",") if x.strip()]

        listener_names = inpdata.get("listeners", "")
        listener_names = [x.strip() for x in listener_names.split(",") if x.strip()]

        qmgr = qmConn(thisqm)
        if qmgr is None:
            classes.Err("ibmmq error:qmgr connection failed for " + str(thisqm))
            return

        qrows = []
        chrows = []
        opt_queues = {}
        opt_channels = {}
        opt_listeners = {}
        opt_qmgr_info = {"status": "running"}
        optadvisor_collect = common.optadvisor_collection_enabled(inpdata)
        qseen = set()
        chseen = set()
        qdkeys = ["name", "data", "jsondata"]
        chdkeys = ["name", "data", "jsondata"]

        if optadvisor_collect:
            opt_qmgr_info = qMgrInfo(qmgr)

        for qn in q:
            queues = {}
            queues = qStat(qmgr, qn, queues)
            queues = qStatInfo(qmgr, qn, queues, optadvisor_collect)
            queues = qResStat(qmgr, qn, queues)

            if queues:
                opt_queues.update(queues)
                for k, v in queues.items():
                    strin = "#".join(str(vin) for kin, vin in v.items() if kin != "name")

                    rowkey = (k, strin)
                    if rowkey not in qseen:
                        qseen.add(rowkey)
                        qrows.append(
                            {
                                "name": k,
                                "data": strin,
                                "jsondata": json.dumps(v),
                            }
                        )

        for ch in chl:
            chls = {}
            chls = chStat(qmgr, ch, chls)

            if chls:
                opt_channels.update(chls)
                for k, v in chls.items():
                    strin = "#".join(str(vin) for kin, vin in v.items() if kin != "name")

                    rowkey = (k, strin)
                    if rowkey not in chseen:
                        chseen.add(rowkey)
                        chrows.append(
                            {
                                "name": k,
                                "data": strin,
                                "jsondata": json.dumps(v),
                            }
                        )

        if optadvisor_collect:
            for listener_name in listener_names:
                opt_listeners = listenerStat(qmgr, listener_name, opt_listeners)

            scanned_queues = {}
            scanned_queues = qStat(qmgr, "*", scanned_queues)
            scanned_queues = qStatInfo(qmgr, "*", scanned_queues, True)
            if scanned_queues:
                opt_queues = scanned_queues

            try:
                scanned_channels = chStat(qmgr, "*", {})
                if scanned_channels:
                    opt_channels = scanned_channels
            except Exception as ex:
                classes.Err("ibmmq optadvisor channel summary error:" + str(ex))

            try:
                if not opt_listeners:
                    opt_listeners = listenerStat(qmgr, "*", opt_listeners)
            except Exception as ex:
                classes.Err("ibmmq optadvisor listener summary error:" + str(ex))

            payload = buildOptAdvisorPayload(
                thisqm,
                inpdata,
                opt_qmgr_info,
                opt_queues,
                opt_channels,
                opt_listeners,
                _utc_now(),
            )
            if payload is not None:
                _append_optadvisor_payload(thisqm, payload)

        if qrows:
            qrows = sorted(qrows, key=lambda x: x["name"])
            file_utils.WriteCSV(
                "ibmmq_" + str(thisqm) + "_queues",
                qrows,
                qdkeys,
                "a",
            )

        if chrows:
            chrows = sorted(chrows, key=lambda x: x["name"])
            file_utils.WriteCSV(
                "ibmmq_" + str(thisqm) + "_channels",
                chrows,
                chdkeys,
                "a",
            )

    except MQ_ERROR as ex:
        classes.Err("ibmmq error:" + str(ex))
    except Exception as ex:
        classes.Err("ibmmq error:" + str(ex))
    finally:
        if qmgr is not None:
            try:
                qmDisc(qmgr)
            except Exception:
                pass


def depthperc(queue_info):
    if (
        pymqi.CMQC.MQIA_CURRENT_Q_DEPTH not in queue_info
        or pymqi.CMQC.MQIA_MAX_Q_DEPTH not in queue_info
    ):
        return None
    depthcur = queue_info[pymqi.CMQC.MQIA_CURRENT_Q_DEPTH]
    depthmax = queue_info[pymqi.CMQC.MQIA_MAX_Q_DEPTH]
    if depthmax == 0:
        return 0
    depthperc = (depthcur / depthmax) * 100
    return depthperc


def flushOptAdvisorTelemetry(thisqm, website, webssl, _legacy_token, thisdata):
    if not isinstance(thisdata, dict) or not common.optadvisor_enabled(thisdata):
        return

    file = _optadvisor_log_path(thisqm)
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
                res = makerequest.postOptAdvisorTelemetry(webssl, website, payload, common.optadvisor_post_token(thisdata, _legacy_token))
                if res is None or res.status_code < 200 or res.status_code >= 300:
                    remaining.append(line)
            except (json.JSONDecodeError, TypeError, ValueError) as err:
                classes.Err("ibmmq optadvisor payload parse error:" + str(err))
            except Exception as err:
                classes.Err("ibmmq optadvisor post error:" + str(err))
                remaining.append(line)

        with open(file, "w", encoding="utf-8") as f:
            f.writelines(remaining)
    except OSError as err:
        classes.Err("ibmmq optadvisor file error:" + str(err))


def resetStat(thisqm, website, webssl, _legacy_token, thisdata):
    try:
        files = glob.glob(
            os.path.join(os.getcwd(), "logs", "ibmmq_" + thisqm + "_queues.csv")
        )
        for file in files:
            if os.path.isfile(file):
                statlist = {}
                with open(file, newline="", encoding="utf-8") as f:
                    reader_obj = csv.reader(f, delimiter=",")
                    for linearr in reader_obj:
                        if not linearr or len(linearr) < 3:
                            continue
                        if linearr[0] == "name":
                            continue
                        if not str(linearr[0]).strip():
                            continue
                        if not str(linearr[1]).strip():
                            continue
                        if not str(linearr[2]).strip():
                            continue

                        qname = linearr[0]
                        if qname not in statlist:
                            statlist[qname] = {"data": "", "jsondata": {}}

                        statlist[qname]["data"] += linearr[1] + ";"
                        statlist[qname]["jsondata"] = json.loads(linearr[2])

                if len(statlist) > 0:
                    res = makerequest.postibmmqQData(
                        webssl, website, thisqm, json.dumps(statlist)
                    )
                    if res is not None and 200 <= int(res.status_code) < 300:
                        open(file, "w", encoding="utf-8").close()
                    else:
                        classes.Err("ibmmq queue status upload failed for " + str(thisqm))
    except OSError as err:
        classes.Err("Error opening queues file:" + str(err))
    except (json.JSONDecodeError, csv.Error, IndexError, TypeError, ValueError) as err:
        classes.Err("Error parsing queues file:" + str(err))

    try:
        files = glob.glob(
            os.path.join(os.getcwd(), "logs", "ibmmq_" + thisqm + "_channels.csv")
        )
        for file in files:
            if os.path.isfile(file):
                statlist = {}
                with open(file, newline="", encoding="utf-8") as f:
                    reader_obj = csv.reader(f, delimiter=",")
                    for linearr in reader_obj:
                        if not linearr or len(linearr) < 3:
                            continue
                        if linearr[0] == "name":
                            continue
                        if not str(linearr[0]).strip():
                            continue
                        if not str(linearr[1]).strip():
                            continue
                        if not str(linearr[2]).strip():
                            continue

                        chname = linearr[0]
                        if chname not in statlist:
                            statlist[chname] = {"data": "", "jsondata": {}}

                        statlist[chname]["data"] += linearr[1] + ";"
                        statlist[chname]["jsondata"] = json.loads(linearr[2])

                if len(statlist) > 0:
                    res = makerequest.postibmmqCHData(
                        webssl, website, thisqm, json.dumps(statlist)
                    )
                    if res is not None and 200 <= int(res.status_code) < 300:
                        open(file, "w", encoding="utf-8").close()
                    else:
                        classes.Err("ibmmq channel status upload failed for " + str(thisqm))
    except OSError as err:
        classes.Err("Error opening channels file:" + str(err))
    except (json.JSONDecodeError, csv.Error, IndexError, TypeError, ValueError) as err:
        classes.Err("Error parsing channels file:" + str(err))

    flushOptAdvisorTelemetry(thisqm, website, webssl, _legacy_token, thisdata)
