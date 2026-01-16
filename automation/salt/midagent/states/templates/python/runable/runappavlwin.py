import json, subprocess, sys, os, inspect
from datetime import datetime

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import makerequest, classes, configs, statarr, decrypt

now = datetime.now()
current_time = now.strftime("%Y-%m-%d %H:%M:%S")

try:
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
                    cred = {}

                    if "usr" in item and item["usr"]:
                        cred["usr"] = item["usr"]
                    if "pwd" in item and item["pwd"]:
                        cred["pwd"] = decrypt.decryptit(item["pwd"], uid * 4)
                    if "mngmport" in item and item["mngmport"]:
                        cred["mngmport"] = item["mngmport"]
                    if "ssl" in item and item["ssl"]:
                        cred["ssl"] = item["ssl"]

                    if "dockercont" in item:
                        ret = statarr.avlCheck(k, item["dockercont"], cred)
                    else:
                        ret = statarr.avlCheck(k, "", cred)

                    if item["enabled"] == "yes":
                        cmd = ret[srvtype]
                        try:
                            proc = subprocess.run(
                                cmd,
                                shell=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL
                            )
                            out = proc.stdout.decode(errors="ignore")
                            cnt = sum(1 for line in out.splitlines() if k in line)

                            if cnt >= 1:
                                classes.WriteData("online", "avl_" + srvtype + "_" + k + ".csv")
                            else:
                                classes.WriteData("offline", "avl_" + srvtype + "_" + k + ".csv")
                                if "monid" in item:
                                    req = {}
                                    req["appsrv"] = k
                                    req["monid"] = item["monid"]
                                    req["srvid"] = uid
                                    req["srvtype"] = srvtype
                                    req["message"] = "Server not available"
                                    req["alerttime"] = current_time
                                    req["inttoken"] = inttoken
                                    makerequest.postMonAl(webssl, website, json.dumps(req))
                        except subprocess.CalledProcessError as e:
                            classes.Err("avlCheck err:" + str(e))
except Exception as err:
    classes.Err("error in runappavl:" + str(err))
