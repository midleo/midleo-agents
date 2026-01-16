import json, sys, os, inspect

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

    required = {"label", "tool", "keystore", "password"}
    if not required.issubset(CERTINP):
        raise ValueError("Missing required certificate fields")

    try:
        cert_data = configs.getcertData()
    except Exception:
        cert_data = {}

    cert_data[CERTINP["label"]] = {
        "command": CERTINP["tool"],
        "cfile": CERTINP["keystore"],
        "clabel": CERTINP["label"],
        "cpass": decrypt.encrypt(CERTINP["password"], uid * 4)
    }

    cert_path = os.path.join(os.getcwd(), "config", "certs.json")
    with open(cert_path, "w", encoding="utf-8") as cert_file:
        json.dump(cert_data, cert_file)

    print(CERTINP["label"] + " configuration added")

if __name__ == "__main__":
    createCertJson()
