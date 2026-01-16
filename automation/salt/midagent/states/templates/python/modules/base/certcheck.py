import subprocess, json, os
from modules.base import classes, decrypt

def Run(uid):
    try:
        data = []
        with open(os.path.join(os.getcwd(), "config", "certs.json"), "r") as cert_file:
            certlist = json.load(cert_file)

        for attr, value in certlist.items():
            cpass = decrypt.decryptit(value["cpass"], uid)

            if not os.path.isfile(value["cfile"]):
                continue

            certcn = ""
            certvalid = ""

            if value["command"] == "keytool":
                cmd = [
                    "keytool", "-list", "-v",
                    "-keystore", value["cfile"],
                    "-storepass", cpass,
                    "-alias", value["clabel"]
                ]
                out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode("utf-8", errors="ignore")
                for line in out.splitlines():
                    if "Owner:" in line:
                        certcn = line.split("=", 1)[1].split(",", 1)[0].strip()
                    if "until:" in line:
                        certvalid = line.split("until:", 1)[1].strip()

            elif value["command"] == "runmqakm":
                cmd = [
                    "runmqakm", "-cert", "-details",
                    "-db", value["cfile"],
                    "-label", value["clabel"],
                    "-stashed"
                ]
                out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode("utf-8", errors="ignore")
                for line in out.splitlines():
                    if "Subject:" in line and "CN=" in line:
                        certcn = line.split("CN=", 1)[1].strip()
                    if "Not After" in line:
                        certvalid = line.split(":", 1)[1].strip()

            if certcn:
                certdetails = {
                    "CN": value["clabel"],
                    "VALID": certvalid,
                    "FILE": value["cfile"]
                }
                data.append(certdetails)

        return data

    except Exception as err:
        classes.Err("Exception:" + str(err) + " at checkcert()")
        return None
