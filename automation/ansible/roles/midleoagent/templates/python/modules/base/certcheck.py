import subprocess
import json
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from modules.base import classes, decrypt

def _parse_expiry(value):
    if not value:
        return None

    value = value.strip()

    for fmt in (
        "%a %b %d %H:%M:%S %Z %Y",
        "%a %b %d %H:%M:%S %Y",
        "%b %d, %Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except Exception:
            pass

    try:
        dt = parsedate_to_datetime(value)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except Exception:
        return None


def _is_expired(valid_to):
    dt = _parse_expiry(valid_to)
    if not dt:
        return False
    return dt < datetime.now(timezone.utc)


def _get_excluded_aliases(value):
    excludes = value.get("exclude_aliases", "")
    return {x.strip() for x in excludes.split(",") if x.strip()}


def _run_cmd(cmd):
    return subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode(
        "utf-8", errors="ignore"
    )


def _list_keytool_entries(cfile, cpass):
    cmd = ["keytool", "-list", "-v", "-keystore", cfile, "-storepass", cpass]
    out = _run_cmd(cmd)

    entries = []
    current = None

    for line in out.splitlines():
        line = line.strip()

        if line.startswith("Alias name:"):
            if current:
                entries.append(current)
            current = {"alias": line.split(":", 1)[1].strip(), "cn": "", "valid": ""}
            continue

        if not current:
            continue

        if line.startswith("Owner:"):
            owner = line.split(":", 1)[1].strip()
            match = re.search(r"CN=([^,]+)", owner)
            current["cn"] = match.group(1).strip() if match else owner

        if " until: " in line:
            current["valid"] = line.split(" until: ", 1)[1].strip()

    if current:
        entries.append(current)

    return entries


def _list_runmqakm_labels(cfile):
    cmd = ["runmqakm", "-cert", "-list", "all", "-db", cfile, "-stashed"]
    out = _run_cmd(cmd)

    labels = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue

        match = re.search(r"Label\s*:\s*(.+)", line, re.IGNORECASE)
        if match:
            labels.append(match.group(1).strip())
            continue

        match = re.search(r"^\*+\s*(.+?)\s*$", line)
        if match and "certificate" not in line.lower():
            labels.append(match.group(1).strip())

    return list(dict.fromkeys(labels))


def _get_runmqakm_entry(cfile, label):
    cmd = ["runmqakm", "-cert", "-details", "-db", cfile, "-label", label, "-stashed"]
    out = _run_cmd(cmd)

    certcn = ""
    certvalid = ""

    for line in out.splitlines():
        line = line.strip()

        if "Subject:" in line and "CN=" in line:
            match = re.search(r"CN=([^,]+)", line)
            certcn = (
                match.group(1).strip() if match else line.split("CN=", 1)[1].strip()
            )

        if "Not After" in line:
            certvalid = line.split(":", 1)[1].strip()

    return {"alias": label, "cn": certcn, "valid": certvalid}


def Run(uid):
    try:
        data = []
        with open(os.path.join(os.getcwd(), "config", "certs.json"), "r") as cert_file:
            certlist = json.load(cert_file)

        for attr, value in certlist.items():
            cpass = decrypt.decryptit(value["cpass"], uid)

            if not os.path.isfile(value["cfile"]):
                continue

            excluded_aliases = _get_excluded_aliases(value)
            entries = []

            if value["command"] == "keytool":
                entries = _list_keytool_entries(value["cfile"], cpass)

            elif value["command"] == "runmqakm":
                for label in _list_runmqakm_labels(value["cfile"]):
                    entries.append(_get_runmqakm_entry(value["cfile"], label))

            for entry in entries:
                alias = entry.get("alias", "").strip()
                valid = entry.get("valid", "").strip()

                if not alias:
                    continue

                if alias in excluded_aliases:
                    continue

                if _is_expired(valid):
                    continue

                data.append({"CN": alias, "VALID": valid, "FILE": value["cfile"]})

        return data

    except Exception as err:
        classes.Err("Exception:" + str(err) + " at checkcert()")
        return None
