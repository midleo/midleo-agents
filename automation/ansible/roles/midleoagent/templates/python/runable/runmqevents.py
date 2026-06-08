import inspect
import json
import os
import shlex
import subprocess
import sys

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import classes, configs, makerequest

AMQSEVT = os.environ["AMQSEVT"]
MQ_EVENT_TIMEOUT_SECONDS = int(os.environ.get("MIDLEO_MQ_EVENT_TIMEOUT_SECONDS", "20"))


def _mq_event_command(qmgr, queue="SYSTEM.ADMIN.PERFM.EVENT"):
    return (
        shlex.quote(AMQSEVT)
        + " -m "
        + shlex.quote(str(qmgr))
        + " -q "
        + shlex.quote(queue)
        + " -w 1 -o json | jq . -c --slurp"
    )


def _run_mq_event(qmgr, srvtype, item):
    if srvtype == "ibmmqdocker":
        container = item.get("dockercont", "")
        if not container:
            classes.Err("amqsevt skipped missing docker container for " + str(qmgr))
            return []
        command = ["docker", "exec", container, "bash", "-c", _mq_event_command(qmgr)]
    else:
        command = ["sudo", "-u", "mqm", "-i", "/bin/bash", "-lc", _mq_event_command(qmgr)]

    proc = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=MQ_EVENT_TIMEOUT_SECONDS,
        check=False,
        universal_newlines=True,
    )
    output = proc.stdout or ""
    if proc.returncode != 0:
        classes.Err("amqsevt failed for " + str(qmgr) + ":" + output[-1000:])
        return []
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        classes.Err("Return error:" + output[-1000:])
        return []


try:
    avl_data = configs.getAvlData()
    config_data = configs.getcfgData()
    website = config_data["MWADMIN"]
    webssl = config_data["SSLENABLED"]
    uid = config_data["SRVUID"]

    for srvtype, srvinfo in avl_data.items():
        if srvtype not in ("ibmmq", "ibmmqdocker") or not isinstance(srvinfo, dict):
            continue

        for qmgr, item in srvinfo.items():
            if not isinstance(item, dict):
                continue
            try:
                for event in _run_mq_event(qmgr, srvtype, item):
                    event_data = event.get("eventData", {})
                    if event_data.get("baseObjectName") == "SYSTEM.ADMIN.PERFM.EVENT":
                        continue

                    event_table = "\n"
                    for key, val in event_data.items():
                        event_table += str(key) + ": " + str(val) + "\n"

                    ret = {
                        "appsrv": event_data.get("queueMgrName", qmgr),
                        "monid": "MQRC" + str(event.get("eventReason", {}).get("value", "")),
                        "srvid": uid,
                        "appsrvid": item["appsrvid"] if "appsrvid" in item else "none",
                        "srvtype": srvtype,
                        "alerttime": event.get("eventCreation", {}).get("timeStamp", ""),
                        "message": event.get("eventReason", {}).get("name", "") + event_table,
                                    "object": event_data.get("baseObjectName", ""),
                    }
                    makerequest.postMonAl(webssl, website, json.dumps(ret))
            except subprocess.TimeoutExpired:
                classes.Err("amqsevt timed out for " + str(qmgr))

except Exception as err:
    classes.Err("No such configuration file - config/conftrack.json." + str(err))
