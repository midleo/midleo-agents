import base64
import json
from urllib.parse import quote

import requests
import urllib3
from midleo_client import AGENT_VER
from modules.base import classes, configs

DEFAULT_TIMEOUT_SECONDS = 20
MAX_LOG_BODY_BYTES = 2048


def _cfg():
    data = configs.getcfgData() or {}
    timeout_raw = data.get("REQUEST_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
    try:
        timeout = int(timeout_raw)
    except Exception:
        timeout = DEFAULT_TIMEOUT_SECONDS
    timeout = max(1, min(timeout, 120))

    verify = str(data.get("SSLVERIFY", "y")).strip().lower() not in (
        "n",
        "no",
        "false",
        "0",
    )

    return {"timeout": timeout, "verify": verify}


def _headers():
    return {
        "Content-type": "application/json",
        "Accept": "text/plain",
        "User-Agent": "MWAdmin v." + AGENT_VER,
    }


def _base_url(webssl, website):
    website = str(website or "").strip().rstrip("/")
    if website.startswith("http://") or website.startswith("https://"):
        return website

    scheme = "https" if str(webssl).strip().lower() in ("y", "yes", "true", "1") else "http"
    return scheme + "://" + website


def _request(method, webssl, website, path, data=None, headers=None, **kwargs):
    options = _cfg()
    url = _base_url(webssl, website) + path
    verify = options["verify"]
    sensitive_response = bool(kwargs.pop("sensitive_response", False))

    if not verify:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    try:
        res = requests.request(
            method,
            url,
            data=data,
            headers=headers or _headers(),
            verify=verify,
            timeout=options["timeout"],
            **kwargs,
        )
        if sensitive_response:
            body = "[redacted]"
        else:
            body = (res.content or b"")[:MAX_LOG_BODY_BYTES].decode(
                "utf-8", errors="replace"
            )
        classes.Err(method.upper() + " " + path + " HTTPResponse:" + str(res.status_code) + " " + body)
        return res
    except requests.exceptions.RequestException as ex:
        classes.Err("Exception:" + str(ex))
        return None


def postData(webssl, website, data):
    _request("post", webssl, website, "/pubapi/updatesrv", json.dumps(data))


def postStatData(webssl, website, thisdata):
    _request("post", webssl, website, "/pubapi/updatestat", thisdata)


def postibmmqQData(webssl, website, qm, data):
    _request(
        "post",
        webssl,
        website,
        "/pubapi/updateibmmqqstat/" + quote(str(qm), safe=""),
        data,
    )


def postibmmqCHData(webssl, website, qm, data):
    _request(
        "post",
        webssl,
        website,
        "/pubapi/updateibmmqchstat/" + quote(str(qm), safe=""),
        data,
    )


def postOptAdvisorTelemetry(webssl, website, data, inttoken=None):
    headers = _headers()
    payload = dict(data or {})
    if inttoken:
        payload["inttoken"] = str(inttoken)
    return _request(
        "post",
        webssl,
        website,
        "/pubapi/updateoptadvisor",
        json.dumps(payload),
        headers=headers,
    )


def postOptAdvisorCollectorToken(webssl, website, data, inttoken=None):
    headers = _headers()
    payload = dict(data or {})
    if inttoken:
        payload["inttoken"] = str(inttoken)
    return _request(
        "post",
        webssl,
        website,
        "/pubapi/optadvisorcollectortoken",
        json.dumps(payload),
        headers=headers,
        sensitive_response=True,
    )


def getQRestStat(webssl, website, webport, qmgr, queue, usr, passwd):
    headers = {
        "Content-Type": "text/plain",
        "charset": "utf-8",
        "User-Agent": "MWAdmin v." + AGENT_VER,
    }
    qmgr_path = quote(str(qmgr), safe="")
    queue_path = quote(str(queue), safe="")
    base = str(website or "").strip()
    if not base.startswith("http://") and not base.startswith("https://"):
        scheme = "https" if str(webssl).strip().lower() in ("y", "yes", "true", "1") else "http"
        base = scheme + "://" + base
    if webport:
        base = base.rstrip("/") + ":" + str(webport)

    path = (
        "/ibmmq/rest/v1/admin/qmgr/"
        + qmgr_path
        + "/queue/"
        + queue_path
        + "?type=local&attributes=storage.maximumDepth&status=status"
    )
    res = _request(
        "get",
        webssl,
        base,
        path,
        headers=headers,
        auth=(usr, base64.b64decode(passwd).decode("utf-8").rstrip()),
    )
    if res is not None and res.status_code == 200:
        return res.json()
    return "{}"


def postTrackData(webssl, website, thisdata):
    _request("post", webssl, website, "/pubapi/updateibmqtrack", thisdata)


def postAvlData(webssl, website, thisdata):
    _request("post", webssl, website, "/pubapi/updateappsrvavl", thisdata)


def postMonAl(webssl, website, thisdata):
    _request("post", webssl, website, "/pubapi/monalert", thisdata)


def postMonCheck(webssl, website, thisdata):
    _request("post", webssl, website, "/pubapi/extmoncheck", thisdata)


def postMaintenance(webssl, website, data):
    _request("post", webssl, website, "/pubapi/servermaintenance", json.dumps(data))
