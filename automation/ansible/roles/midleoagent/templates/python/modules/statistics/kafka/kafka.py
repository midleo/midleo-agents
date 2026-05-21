import json
import os

from modules.base import classes
from modules.statistics import common


def getStat(thisqm, inpdata):
    try:
        metrics = common.parse_json_object(inpdata)
        jar_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "resources",
            "midleo_kafka.jar",
        )
        java_arg = json.dumps(
            {
                "logdir": common.first_value(metrics),
                "mbean": ",".join(metrics.keys()),
                "function": "localstat",
                "localbrk": thisqm,
            }
        )

        common.run_command(
            [
                "java",
                "-cp",
                "/midleolibs/libs/*:" + jar_path,
                "midleo_kafka.kafka_main",
                java_arg,
            ],
            "kafka",
        )

    except (json.JSONDecodeError, TypeError, ValueError) as err:
        classes.Err("Error in kafka statistics:" + str(err))


def resetStat(thisnode, website, webssl, inttoken, stat_data):
    common.post_csv_stats(
        "kafka",
        "kafka",
        website,
        webssl,
        inttoken,
        stat_data,
        lambda logdir, subtype: logdir + "Statistics_" + subtype + ".csv",
    )
