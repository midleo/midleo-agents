import base64
import csv
import hashlib
import json
import os

from Crypto.Hash import MD4
import winrm

from modules.base import classes
from modules.statistics import common
from modules.statistics.msiis.modules import srvinfo

_original_hashlib_new = hashlib.new


def md4_patched(name, data=b''):
    if name == 'md4':
        h = MD4.new()
        h.update(data)
        return h
    return _original_hashlib_new(name, data)


hashlib.new = md4_patched


def _decode_password(value):
    if not value:
        return ""
    padded = value + "=" * (4 - len(value) % 4)
    return base64.b64decode(padded).decode("utf-8")


def getStat(thisqm, inpdata):
    try:
        inpdata = common.parse_json_object(inpdata)
        values, metrics = common.pop_fields(
            inpdata, {"usr": "", "pwd": "", "mngmport": "", "ssl": ""}
        )

        scheme = "https" if values["ssl"] else "http"
        session_url = scheme + "://" + str(thisqm) + ":" + str(values["mngmport"]) + "/wsman"
        session = winrm.Session(
            session_url,
            auth=(values["usr"], _decode_password(values["pwd"])),
            transport='ntlm',
            server_cert_validation=os.environ.get("MIDLEO_WINRM_CERT_VALIDATION", "ignore"),
            operation_timeout_sec=10,
            read_timeout_sec=20,
        )
        functions = srvinfo.SRVFUNC() if hasattr(srvinfo, 'SRVFUNC') else {}

        for key, logdir in metrics.items():
            ps_script = functions.get(key)
            if not ps_script:
                continue

            result = session.run_ps(ps_script.format(serverName=thisqm))
            output = result.std_out.decode('utf-8', errors='ignore')
            json_data = json.loads(output)
            if not isinstance(json_data, list) or not json_data:
                continue

            filename = os.path.join(logdir, "Statistics_" + key + ".csv")
            file_exists = os.path.isfile(filename)
            with open(filename, mode='a', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=json_data[0].keys())
                if not file_exists:
                    writer.writeheader()
                writer.writerows(json_data)

    except (json.JSONDecodeError, OSError, TypeError, ValueError, winrm.exceptions.WinRMError) as err:
        classes.Err("Error in msiis statistics:" + str(err))


def resetStat(thisnode, website, webssl, inttoken, stat_data):
    common.post_csv_stats(
        "msiis",
        "msiis",
        website,
        webssl,
        inttoken,
        stat_data,
        lambda logdir, subtype: logdir + "Statistics_" + subtype + ".csv",
    )
