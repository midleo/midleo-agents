import json, sys, os, inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import makerequest, classes, configs, file_utils


def _arg(index, name):
    try:
        value = sys.argv[index]
    except IndexError:
        raise ValueError("Missing required argument: " + name)
    value = str(value).strip()
    if not value:
        raise ValueError("Empty required argument: " + name)
    return value

try:
    YM = _arg(1, "YM")
    WD = _arg(2, "WD")
    avl_data = configs.getAvlData()
    config_data = configs.getcfgData()
    website = config_data["MWADMIN"]
    webssl = config_data["SSLENABLED"]
    inttoken = config_data["INTTOKEN"]
    uid = config_data["SRVUID"]
    if len(avl_data) > 0:
        for srvtype, srvinfo in avl_data.items():
            if len(srvinfo.items()) > 0:
                for k, item in srvinfo.items():
                    ret = file_utils.ReadAvl("avl_" + srvtype + "_" + k + ".csv")
                    if "navl" in ret:
                        ret["appsrv"] = k
                        ret["appsrvid"] = (
                            item["appsrvid"] if "appsrvid" in item else "none"
                        )
                        ret["srvid"] = uid
                        ret["inttoken"] = inttoken
                        ret["srvtype"] = srvtype
                        ret["thismonth"] = YM
                        ret["thisdate"] = WD
                        makerequest.postAvlData(webssl, website, json.dumps(ret))

except Exception as err:
    classes.Err("No such configuration file - config/confavl.json." + str(err))
