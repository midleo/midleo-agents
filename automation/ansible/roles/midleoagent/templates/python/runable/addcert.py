import json
import sys
import os
import inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import decrypt, configs

CERTDATA = sys.argv[1]

def createCertJson():
    config_data = configs.getcfgData()
    uid = config_data.get("SRVUID")

    if not uid:
        raise RuntimeError("SRVUID is not set")

    try:
        certinp = json.loads(CERTDATA)
    except Exception:
        raise ValueError("Invalid CERTDATA JSON")

    required = {"tool", "keystore", "password"}
    if not required.issubset(certinp):
        raise ValueError("Missing required certificate fields")

    label = str(certinp.get("label", "")).strip()
    excluded = str(certinp.get("excluded", "")).strip()
    entry_key = label if label else certinp["keystore"]

    entry = {
        "command": certinp["tool"],
        "cfile": certinp["keystore"],
        "cpass": decrypt.encrypt(certinp["password"], uid * 4),
    }

    if label:
        entry["clabel"] = label

    if excluded:
        entry["exclude_aliases"] = excluded

    configs.upsertSectionItem("certs", entry_key, entry)
    print((label if label else entry_key) + " configuration added")

if __name__ == "__main__":
    createCertJson()
