import json, glob, os, csv, socket, uuid
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


def _append_optadvisor_payload(thisqm, payload):
    os.makedirs(os.path.join(os.getcwd(), "logs"), exist_ok=True)
    with open(_optadvisor_log_path(thisqm), "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n")


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
                queues[qname]["opincount"] = queue_info[
                    pymqi.CMQC.MQIA_OPEN_INPUT_COUNT
                ]
                queues[qname]["opoutcount"] = queue_info[
                    pymqi.CMQC.MQIA_OPEN_OUTPUT_COUNT
                ]
                queues[qname]["uncmess"] = queue_info[
                    pymqi.CMQCFC.MQIACF_UNCOMMITTED_MSGS
                ]
                queues[qname]["oldmessage"] = queue_info[
                    pymqi.CMQCFC.MQIACF_OLDEST_MSG_AGE
                ]
                queues[qname]["lastget"] = (
                    queue_info[pymqi.CMQCFC.MQCACF_LAST_GET_DATE]
                    .decode("utf-8")
                    .strip()
                    + " "
                    + queue_info[pymqi.CMQCFC.MQCACF_LAST_GET_TIME]
                    .decode("utf-8")
                    .strip()
                )
                queues[qname]["lastput"] = (
                    queue_info[pymqi.CMQCFC.MQCACF_LAST_PUT_DATE]
                    .decode("utf-8")
                    .strip()
                    + " "
                    + queue_info[pymqi.CMQCFC.MQCACF_LAST_PUT_TIME]
                    .decode("utf-8")
                    .strip()
                )
    except MQ_ERROR as ex:
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
                chls[chlname]["buff_received"] = chl_info[
                    pymqi.CMQCFC.MQIACH_BUFFERS_RCVD
                ]
                chls[chlname]["indoubt_status"] = chl_info[
                    pymqi.CMQCFC.MQIACH_INDOUBT_STATUS
                ]
    except MQ_ERROR as ex:
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


def _queue_resource(qname, qdata, qmgr_info):
    metrics = []
    _add_metric(metrics, _number_metric("current_depth", qdata.get("curdepth")))
    _add_metric(metrics, _number_metric("max_depth", qdata.get("maxdepth")))
    _add_metric(metrics, _number_metric("depth_percent", qdata.get("percfull")))
    _add_metric(metrics, _number_metric("open_input_count", qdata.get("opincount")))
    _add_metric(metrics, _number_metric("open_output_count", qdata.get("opoutcount")))
    _add_metric(metrics, _number_metric("oldest_message_age_seconds", qdata.get("oldmessage")))
    _add_metric(metrics, _boolean_metric("inhibit_get", qdata.get("inhibit_get")))
    _add_metric(metrics, _boolean_metric("inhibit_put", qdata.get("inhibit_put")))

    dlq = _safe_text(qmgr_info.get("dead_letter_queue"))
    return {
        "resource_type": "mq_queue",
        "technical_key": qname,
        "name": qname,
        "status": "running",
        "parent_technical_key": None,
        "metadata": {
            "queue_type": "local",
            "is_dead_letter_queue": bool(dlq and qname == dlq),
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

    appcode = _safe_text(inpdata.get("appcode"))
    server_id = _safe_text(_get_server_id(inpdata, thisqm))
    if not appcode or not server_id:
        classes.Err("ibmmq optadvisor disabled for missing appcode or server_id")
        return None

    resources = []
    for qname, qdata in sorted((queues or {}).items()):
        resource = _queue_resource(_safe_text(qname), qdata or {}, qmgr_info or {})
        if resource["metrics"]:
            resources.append(resource)

    for chname, chdata in sorted((channels or {}).items()):
        resource = _channel_resource(_safe_text(chname), chdata or {})
        if resource["metrics"]:
            resources.append(resource)

    for listener_name, listener_data in sorted((listeners or {}).items()):
        resource = _listener_resource(_safe_text(listener_name), listener_data or {})
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
        "appcode": appcode,
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


def flushOptAdvisorTelemetry(thisqm, website, webssl, inttoken, thisdata):
    if not isinstance(thisdata, dict) or not common.optadvisor_collection_enabled(thisdata):
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
                payload.pop("inttoken", None)
                res = makerequest.postOptAdvisorTelemetry(webssl, website, payload, common.optadvisor_post_token(thisdata, inttoken))
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


def resetStat(thisqm, website, webssl, inttoken, thisdata):
    try:
        files = glob.glob(
            os.path.join(os.getcwd(), "logs", "ibmmq_" + thisqm + "_queues.csv")
        )
        for file in files:
            if os.path.isfile(file):
                statlist = {"inttoken": inttoken}
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

                if len(statlist) > 1:
                    makerequest.postibmmqQData(
                        webssl, website, thisqm, json.dumps(statlist)
                    )
                    open(file, "w", encoding="utf-8").close()
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
                statlist = {"inttoken": inttoken}
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

                if len(statlist) > 1:
                    makerequest.postibmmqCHData(
                        webssl, website, thisqm, json.dumps(statlist)
                    )
                    open(file, "w", encoding="utf-8").close()
    except OSError as err:
        classes.Err("Error opening channels file:" + str(err))
    except (json.JSONDecodeError, csv.Error, IndexError, TypeError, ValueError) as err:
        classes.Err("Error parsing channels file:" + str(err))

    flushOptAdvisorTelemetry(thisqm, website, webssl, inttoken, thisdata)
