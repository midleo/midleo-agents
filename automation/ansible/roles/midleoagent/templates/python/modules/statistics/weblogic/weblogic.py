import json
import os

from modules.base import classes
from modules.statistics import common


def getStat(thisqm, inpdata):
    try:
        inpdata = common.parse_json_object(inpdata)
        values, metrics = common.pop_fields(
            inpdata, {"usr": "", "pwd": "", "mngmport": "", "ssl": "no"}
        )
        jar_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "resources",
            "midleo_weblogic.jar",
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
                "ssl": values["ssl"],
            }
        )

        common.run_command(
            [
                "java",
                "--add-opens",
                "java.base/java.io=ALL-UNNAMED",
                "-cp",
                "/midleolibs/libs/*:/midleolibs/vendor/*:" + jar_path,
                "midleo_weblogic.weblogic_main",
                java_arg,
            ],
            "weblogic",
        )

    except (json.JSONDecodeError, TypeError, ValueError) as err:
        classes.Err("Error in weblogic statistics:" + str(err))


def resetStat(thisnode, website, webssl, inttoken, stat_data):
    common.post_csv_stats(
        "weblogic",
        "weblogic",
        website,
        webssl,
        inttoken,
        stat_data,
        lambda logdir, subtype: logdir + "Statistics_" + subtype + ".csv",
    )
