import json, glob, os, csv
from modules.base import classes, file_utils, makerequest
from datetime import datetime

try:
    import pymqi
except:
    pass


def qmConn(thisqm):
    try:
        qmgr = pymqi.connect(thisqm)
    except pymqi.MQMIError as ex:
        classes.Err("Exception:" + str(ex))
        qmgr = None
    return qmgr


def qmDisc(thisqm):
    thisqm.disconnect()


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
    except pymqi.MQMIError as ex:
        classes.Err("Exception:" + str(ex))
    return queues


def qStatInfo(thisqm, q, queues):
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
    except pymqi.MQMIError as ex:
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
    except pymqi.MQMIError as ex:
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
                chls[chlname]["bytes_received"] = chl_info[
                    pymqi.CMQCFC.MQIACH_BUFFERS_RECEIVED
                ]
                chls[chlname]["buff_sent"] = chl_info[pymqi.CMQCFC.MQIACH_BUFFERS_SENT]
                chls[chlname]["buff_received"] = chl_info[
                    pymqi.CMQCFC.MQIACH_BUFFERS_RCVD
                ]
                chls[chlname]["indoubt_status"] = chl_info[
                    pymqi.CMQCFC.MQIACH_INDOUBT_STATUS
                ]
    except pymqi.MQMIError as ex:
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


def getStat(thisqm, inpdata):
    qmgr = None
    try:
        inpdata = json.loads(inpdata)

        q = inpdata.get("queues", "")
        q = [x.strip() for x in q.split(",") if x.strip()]

        chl = inpdata.get("channels", "")
        chl = [x.strip() for x in chl.split(",") if x.strip()]

        qmgr = qmConn(thisqm)
        if qmgr is None:
            classes.Err("ibmmq error:qmgr connection failed for " + str(thisqm))
            return

        qrows = []
        chrows = []
        qseen = set()
        chseen = set()
        qdkeys = ["name", "data", "jsondata"]
        chdkeys = ["name", "data", "jsondata"]

        for qn in q:
            queues = {}
            queues = qStat(qmgr, qn, queues)
            queues = qStatInfo(qmgr, qn, queues)
            queues = qResStat(qmgr, qn, queues)

            if queues:
                for k, v in queues.items():
                    strin = ""
                    for kin, vin in v.items():
                        if kin != "name":
                            strin += str(vin) + "#"
                    strin = strin[:-1] if strin else ""

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
                for k, v in chls.items():
                    strin = ""
                    for kin, vin in v.items():
                        if kin != "name":
                            strin += str(vin) + "#"
                    strin = strin[:-1] if strin else ""

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

    except pymqi.MQMIError as ex:
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
    depthperc = (depthcur / depthmax) * 100
    return depthperc

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
