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
        CERTINP = json.loads(CERTDATA)
    except Exception:
        raise ValueError("Invalid CERTDATA JSON")

    required = {"tool", "keystore", "password"}
    if not required.issubset(CERTINP):
        raise ValueError("Missing required certificate fields")

    label = str(CERTINP.get("label", "")).strip()
    excluded = str(CERTINP.get("excluded", "")).strip()

    try:
        cert_data = configs.getcertData()
    except Exception:
        cert_data = {}

    entry_key = label if label else CERTINP["keystore"]

    cert_data[entry_key] = {
        "command": CERTINP["tool"],
        "cfile": CERTINP["keystore"],
        "cpass": decrypt.encrypt(CERTINP["password"], uid * 4),
    }

    if label:
        cert_data[entry_key]["clabel"] = label

    if excluded:
        cert_data[entry_key]["exclude_aliases"] = excluded

    cert_path = os.path.join(os.getcwd(), "config", "certs.json")
    with open(cert_path, "w", encoding="utf-8") as cert_file:
        json.dump(cert_data, cert_file)

    print((label if label else entry_key) + " configuration added")


if __name__ == "__main__":
    createCertJson()
