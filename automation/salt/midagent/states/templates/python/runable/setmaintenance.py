import json
import os
import inspect
import sys

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import makerequest, classes, configs


def create():
    try:
        config_data = configs.getcfgData()
        uid = config_data['SRVUID']
        inttoken = config_data['INTTOKEN']

        if len(sys.argv) < 2:
            return {"error": "usage: setmaintenance.py on|off [comment]"}

        state = str(sys.argv[1]).strip().lower()
        comment = " ".join(sys.argv[2:]).strip() if len(sys.argv) > 2 else ""

        if state not in ("on", "off"):
            return {"error": "usage: setmaintenance.py on|off [comment]"}

        return {
            "uid": uid,
            "inttoken": inttoken,
            "srvmaintenance": 1 if state == "on" else 0,
            "comment": comment
        }

    except OSError as err:
        classes.Err("Error in create:" + str(err))
    except Exception as ex:
        classes.Err("Exception in create:" + str(ex))


def main():
    data = create()
    config_data = configs.getcfgData()
    website = config_data['MWADMIN']
    webssl = config_data['SSLENABLED']

    if not data or 'error' in data:
        return

    try:
        makerequest.postMaintenance(webssl, website, data)
    except OSError as err:
        classes.Err("Error in main:" + str(err))
    except Exception as ex:
        classes.Err("Exception in main:" + str(ex))


if __name__ == '__main__':
    main()