import json
import os
import shlex

from modules.base import classes
from modules.statistics import common


def getStat(thisqm, inpdata):
    try:
        inpdata = common.parse_json_object(inpdata)
        container = str(inpdata.pop("container", "")).strip()
        if not container:
            raise ValueError("container is required")

        script = os.path.join(os.environ["MWAGTDIR"], "magent_docker.sh")
        thisscript = (
            shlex.quote(script)
            + " getdockerstat ibmmq "
            + shlex.quote(str(thisqm))
            + " "
            + shlex.quote(json.dumps(inpdata))
        )

        common.run_command(
            ["docker", "exec", container, "bash", "-c", thisscript],
            "ibmmqdocker",
        )

    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as err:
        classes.Err("Error in ibmmqdocker statistics:" + str(err))
