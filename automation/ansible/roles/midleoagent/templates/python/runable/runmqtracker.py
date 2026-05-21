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


def _mq_event_command(qmgr):
    return (
        shlex.quote(AMQSEVT)
        + " -m "
        + shlex.quote(str(qmgr))
        + " -q SYSTEM.ADMIN.TRACE.ACTIVITY.QUEUE -w 1 -o json | jq . -c --slurp"
    )


def _run_mq_event(qmgr):
    proc = subprocess.run(
        ["sudo", "su", "-", "mqm", "-c", _mq_event_command(qmgr)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=MQ_EVENT_TIMEOUT_SECONDS,
        check=False,
    )
    output = proc.stdout.decode(errors="replace")
    if proc.returncode != 0:
        classes.Err("amqsevt failed for " + str(qmgr) + ":" + output[-1000:])
        return []
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        classes.Err("Return error:" + output[-1000:])
        return []


try:
    track_data = configs.gettrackData()
    config_data = configs.getcfgData()
    website = config_data["MWADMIN"]
    webssl = config_data["SSLENABLED"]
    inttoken = config_data["INTTOKEN"]

    for qmgr in track_data.keys():
        try:
            for event in _run_mq_event(qmgr):
                event_data = event.get("eventData", {})
                channel_name = event_data.get("channelName", "Local")
                connection_name = event_data.get("connectionName", "Local     ")
                app = event_data.get("applName", "")
                for act in event_data.get("activityTrace", []):
                    if (
                        act.get("operationId") in ["Put1", "Put", "Get", "Cb", "Callback"]
                        and act.get("objectName") != "SYSTEM.ADMIN.TRACE.ACTIVITY.QUEUE"
                    ):
                        ret = {
                            "qmgr": qmgr,
                            "objectName": act.get("objectName", ""),
                            "applName": app,
                            "channelName": channel_name,
                            "connectionName": connection_name,
                            "trackdata": act,
                            "inttoken": inttoken,
                        }
                        makerequest.postTrackData(webssl, website, json.dumps(ret))
        except subprocess.TimeoutExpired:
            classes.Err("amqsevt timed out for " + str(qmgr))

except Exception as err:
    classes.Err("No such configuration file - config/conftrack.json." + str(err))
