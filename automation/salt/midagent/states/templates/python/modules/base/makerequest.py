import base64
import json
import socket
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

import requests
import urllib3
from midleo_client import AGENT_VER
from modules.base import classes, configs

DEFAULT_TIMEOUT_SECONDS = 20
MAX_LOG_BODY_BYTES = 2048
_REGISTER_ATTEMPTED = False


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


def _with_agent_headers(headers):
    merged = dict(headers or {})
    identity = configs.getAgentIdentity()
    if identity.get("agent_id") and identity.get("agent_token"):
        merged["X-Midleo-Agent-Id"] = str(identity["agent_id"])
        merged["X-Midleo-Agent-Token"] = str(identity["agent_token"])
        merged["X-Midleo-Timestamp"] = str(int(time.time()))
        merged["X-Midleo-Nonce"] = uuid.uuid4().hex
    return merged


def _base_url(webssl, website):
    website = str(website or "").strip().rstrip("/")
    if website.startswith("http://") or website.startswith("https://"):
        return website

    scheme = "https" if str(webssl).strip().lower() in ("y", "yes", "true", "1") else "http"
    return scheme + "://" + website


def _utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso_now():
    return _utc_now().isoformat().replace("+00:00", "Z")


def _record_upload_result(path, status_code=None, error=""):
    if not str(path or "").startswith("/pubapi/"):
        return
    try:
        state = configs.getUploadState()
        if not isinstance(state, dict):
            state = {}
        endpoints = state.get("endpoints")
        if not isinstance(endpoints, dict):
            endpoints = {}
        endpoint = endpoints.get(path)
        if not isinstance(endpoint, dict):
            endpoint = {}

        ok = status_code is not None and int(status_code) >= 200 and int(status_code) < 300
        state["last_attempt_at"] = _iso_now()
        state["last_attempt_ts"] = int(time.time())
        state["last_path"] = str(path)
        state["total_attempts"] = int(state.get("total_attempts", 0)) + 1

        endpoint["last_attempt_at"] = state["last_attempt_at"]
        endpoint["last_status_code"] = status_code
        endpoint["attempts"] = int(endpoint.get("attempts", 0)) + 1

        if ok:
            state["last_success_at"] = state["last_attempt_at"]
            state["last_success_ts"] = state["last_attempt_ts"]
            state["last_success_path"] = str(path)
            state["success_count"] = int(state.get("success_count", 0)) + 1
            state["consecutive_failures"] = 0
            endpoint["last_success_at"] = state["last_attempt_at"]
            endpoint["success_count"] = int(endpoint.get("success_count", 0)) + 1
        else:
            state["last_failure_at"] = state["last_attempt_at"]
            state["last_failure_ts"] = state["last_attempt_ts"]
            state["last_failure_path"] = str(path)
            state["last_failure_status_code"] = status_code
            state["last_failure_error"] = str(error or "")[-512:]
            state["failure_count"] = int(state.get("failure_count", 0)) + 1
            state["consecutive_failures"] = int(state.get("consecutive_failures", 0)) + 1
            endpoint["last_failure_at"] = state["last_attempt_at"]
            endpoint["failure_count"] = int(endpoint.get("failure_count", 0)) + 1
            endpoint["last_error"] = str(error or "")[-512:]

        endpoints[path] = endpoint
        state["endpoints"] = endpoints
        configs.saveUploadState(state)
    except Exception:
        pass


def _drop_legacy_auth_payload_field(value):
    if isinstance(value, dict):
        cleaned = dict(value)
        cleaned.pop("inttoken", None)
        return cleaned
    if isinstance(value, list):
        return [_drop_legacy_auth_payload_field(item) for item in value]
    return value


def _strip_legacy_auth_payload(data):
    if data is None:
        return None
    if isinstance(data, (dict, list)):
        return _drop_legacy_auth_payload_field(data)
    if isinstance(data, bytes):
        raw = data.decode("utf-8", errors="replace")
    elif isinstance(data, str):
        raw = data
    else:
        return data
    try:
        parsed = json.loads(raw)
    except Exception:
        return data
    cleaned = _drop_legacy_auth_payload_field(parsed)
    return json.dumps(cleaned)


def _register_agent_identity(webssl, website):
    global _REGISTER_ATTEMPTED
    if configs.getAgentIdentity():
        return True
    if _REGISTER_ATTEMPTED:
        return False
    _REGISTER_ATTEMPTED = True
    cfg = configs.getcfgData() or {}
    bootstrap_token = str(cfg.get("INTTOKEN", "")).strip()
    if not bootstrap_token:
        return False
    payload = {
        "inttoken": bootstrap_token,
        "hostname": socket.gethostname(),
        "serverid": str(cfg.get("SRVUID", "")).strip(),
        "appsrv_id": str(cfg.get("APPSRV_ID", "")).strip(),
        "environment": str(cfg.get("ENVIRONMENT", cfg.get("ENV", ""))).strip(),
        "agent_name": str(cfg.get("AGENT_NAME", socket.gethostname())).strip(),
        "agent_version": AGENT_VER,
        "agent_type": str(cfg.get("AGENT_TYPE", "python")).strip() or "python",
        "installation_id": configs.getInstallationId(),
    }
    res = _request(
        "post",
        webssl,
        website,
        "/pubapi/registeragent",
        json.dumps(payload),
        headers=_headers(),
        sensitive_response=True,
        skip_agent_enrollment=True,
    )
    if res is None or res.status_code != 200:
        return False
    try:
        body = res.json()
    except Exception:
        return False
    agent_id = body.get("agent_id")
    agent_token = body.get("agent_token")
    if agent_id and agent_token:
        configs.saveAgentIdentity(
            agent_id,
            agent_token,
            {
                "installation_id": payload["installation_id"],
                "enrollment_mode": body.get("enrollment_mode", "auto"),
                "status": body.get("status", "active"),
            },
        )
        classes.Err("Agent identity saved for " + str(agent_id))
        return True
    return False


def _request(method, webssl, website, path, data=None, headers=None, **kwargs):
    options = _cfg()
    url = _base_url(webssl, website) + path
    verify = options["verify"]
    sensitive_response = bool(kwargs.pop("sensitive_response", False))
    skip_agent_enrollment = bool(kwargs.pop("skip_agent_enrollment", False))
    request_headers = headers or _headers()
    if path.startswith("/pubapi/") and not skip_agent_enrollment:
        if not _register_agent_identity(webssl, website):
            classes.Err("Agent identity is missing; request not sent for " + path)
            _record_upload_result(path, None, "agent identity is missing")
            return None
        request_headers = _with_agent_headers(request_headers)
        data = _strip_legacy_auth_payload(data)

    if not verify:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    try:
        res = requests.request(
            method,
            url,
            data=data,
            headers=request_headers,
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
        _record_upload_result(path, res.status_code, body if res.status_code < 200 or res.status_code >= 300 else "")
        return res
    except requests.exceptions.RequestException as ex:
        classes.Err("Exception:" + str(ex))
        _record_upload_result(path, None, str(ex))
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


def postOptAdvisorTelemetry(webssl, website, data, _legacy_token=None):
    headers = _headers()
    payload = dict(data or {})
    return _request(
        "post",
        webssl,
        website,
        "/pubapi/updateoptadvisor",
        json.dumps(payload),
        headers=headers,
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
