import json
import os

from modules.base import classes
from modules.statistics import common


def getStat(thisqm, inpdata):
    try:
        inpdata = common.parse_json_object(inpdata)
        values, metrics = common.pop_fields(
            inpdata, {"usr": "", "pwd": "", "mngmport": ""}
        )
        jar_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "resources",
            "midleo_jboss.jar",
        )
        java_arg = json.dumps(
            {
                "logdir": common.first_value(metrics),
                "server": thisqm,
                "mbean": ",".join(metrics.keys()),
                "function": "getstat",
                "usr": values["usr"],
                "pwd": values["pwd"],
                "mngmport": values["mngmport"],
            }
        )

        common.run_command(
            [
                "java",
                "-cp",
                "/midleolibs/libs/*:" + jar_path,
                "midleo_jboss.midleo_jboss",
                java_arg,
            ],
            "jboss",
        )

    except (json.JSONDecodeError, TypeError, ValueError) as err:
        classes.Err("Error in jboss statistics:" + str(err))


def resetStat(thisnode, website, webssl, inttoken, stat_data):
    common.post_csv_stats(
        "jboss",
        "jboss",
        website,
        webssl,
        inttoken,
        stat_data,
        lambda logdir, subtype: logdir + "Statistics_" + subtype + ".csv",
    )
