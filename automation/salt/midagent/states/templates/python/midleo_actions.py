#!/usr/bin/env python3

import json
import os
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from modules.base import classes, configs, makerequest

HOST = "127.0.0.1"
PORT_NUMBER = 5551
MAX_BODY_BYTES = 256 * 1024
DEFAULT_COOLDOWN_SECONDS = 600
DEFAULT_ALERT_COOLDOWN_SECONDS = 600

BASE_DIR = os.getcwd()
CONFIG_DIR = os.path.join(BASE_DIR, "config")
ACTION_CONFIG_FILE = os.path.join(CONFIG_DIR, "confactions.json")
STATE_FILE = os.path.join(CONFIG_DIR, "actions_state.json")

STATE_LOCK = threading.Lock()


def _now():
    return datetime.now()


def _now_str():
    return _now().strftime("%Y-%m-%d %H:%M:%S")


def _read_json(path, default=None):
    if default is None:
        default = {}
    try:
        with open(path, "r", encoding="utf-8") as file_handle:
            data = json.load(file_handle)
            return data if isinstance(data, dict) else default
    except Exception:
        return default


def _write_json_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=".tmp_actions_", dir=os.path.dirname(path)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            json.dump(data, tmp_file, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _load_runtime_config():
    cfg = configs.getcfgData() or {}
    return {
        "uid": str(cfg.get("SRVUID", "")),
        "website": str(cfg.get("MWADMIN", "")),
        "webssl": str(cfg.get("SSLENABLED", "n")),
        "inttoken": str(cfg.get("INTTOKEN", "")),
    }


def _get_action_definitions():
    return _read_json(ACTION_CONFIG_FILE, {})


def _get_state():
    return _read_json(STATE_FILE, {})


def _save_state(state):
    _write_json_atomic(STATE_FILE, state)


def _normalize_key(payload):
    appserver_type = str(payload.get("appserver_type", "")).strip()
    error_code = str(payload.get("error_code", "")).strip()
    if not appserver_type or not error_code:
        raise ValueError("appserver_type and error_code are required")
    return appserver_type, error_code, appserver_type + "." + error_code


def _resolve_script_command(script_path, args):
    args = [str(arg) for arg in (args or [])]

    if os.name == "nt":
        lower_name = script_path.lower()
        if lower_name.endswith(".ps1"):
            return ["powershell", "-File", script_path, *args]
        if lower_name.endswith(".bat") or lower_name.endswith(".cmd"):
            return [script_path, *args]
        return [script_path, *args]

    if script_path.endswith(".sh"):
        return ["/bin/bash", script_path, *args]

    return [script_path, *args]


def _start_action(action_key, action_cfg, payload):
    script_path = str(action_cfg.get("script", "")).strip()
    if not script_path:
        raise ValueError("action has no script")
    if not os.path.isfile(script_path):
        raise FileNotFoundError("script not found: " + script_path)

    payload_json = json.dumps(payload, ensure_ascii=False)
    action_args = action_cfg.get("args", [])
    if not isinstance(action_args, list):
        action_args = []

    fmt_context = {
        "action_key": action_key,
        "appserver_type": str(payload.get("appserver_type", "")),
        "error_code": str(payload.get("error_code", "")),
        "payload": payload_json,
    }
    for key, value in payload.items():
        if isinstance(key, str):
            fmt_context[key] = value

    resolved_args = []
    for item in action_args:
        text = str(item)
        try:
            resolved_args.append(text.format(**fmt_context))
        except Exception:
            resolved_args.append(text)

    env = os.environ.copy()
    env["MIDLEO_ACTION_KEY"] = action_key
    env["MIDLEO_ACTION_PAYLOAD"] = payload_json

    process = subprocess.Popen(
        _resolve_script_command(script_path, resolved_args),
        cwd=BASE_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
    )

    return {
        "pid": process.pid,
        "script": script_path,
        "args": resolved_args,
        "started_at": _now_str(),
        "started_ts": int(time.time()),
    }


def _build_alert(runtime_cfg, action_key, action_cfg, state_entry, payload):
    appserver_type = str(payload.get("appserver_type", ""))
    appsrv = str(
        payload.get("appsrv")
        or payload.get("appserver")
        or action_cfg.get("appsrv")
        or appserver_type
    )
    last_started = state_entry.get("started_at", "")
    script_path = state_entry.get("script", "")
    cooldown = int(action_cfg.get("cooldown_seconds", DEFAULT_COOLDOWN_SECONDS))
    default_message = (
        "Repeated error "
        + action_key
        + " for "
        + appsrv
        + ". Script "
        + script_path
        + " was already started at "
        + last_started
        + "; new execution suppressed for "
        + str(cooldown)
        + " seconds."
    )

    return {
        "appsrv": appsrv,
        "monid": str(action_cfg.get("monid", action_key)),
        "appsrvid": str(action_cfg.get("appsrvid", "none")),
        "srvid": runtime_cfg["uid"],
        "srvtype": appserver_type,
        "message": str(action_cfg.get("message", default_message)),
        "alerttime": _now_str(),
        "inttoken": runtime_cfg["inttoken"],
        "errorcode": str(payload.get("error_code", "")),
        "actionkey": action_key,
        "laststarted": last_started,
        "script": script_path,
        "payload": payload,
    }


def _send_alert(runtime_cfg, action_key, action_cfg, state_entry, payload):
    if not runtime_cfg["website"] or not runtime_cfg["inttoken"] or not runtime_cfg["uid"]:
        classes.Err("midleo_actions missing backend configuration for alert " + action_key)
        return

    alert_data = _build_alert(runtime_cfg, action_key, action_cfg, state_entry, payload)
    makerequest.postMonAl(
        runtime_cfg["webssl"], runtime_cfg["website"], json.dumps(alert_data)
    )


def _handle_action(payload):
    runtime_cfg = _load_runtime_config()
    if not runtime_cfg["uid"]:
        raise ValueError("SRVUID is not configured")

    if "uid" in payload and str(payload.get("uid", "")).strip() != runtime_cfg["uid"]:
        raise ValueError("uid mismatch")

    appserver_type, error_code, action_key = _normalize_key(payload)
    action_map = _get_action_definitions()
    action_cfg = action_map.get(action_key)

    if not isinstance(action_cfg, dict):
        return {
            "status": "ignored",
            "uid": runtime_cfg["uid"],
            "action_key": action_key,
            "message": "No action configured",
        }

    cooldown = int(action_cfg.get("cooldown_seconds", DEFAULT_COOLDOWN_SECONDS))
    alert_cooldown = int(
        action_cfg.get("alert_cooldown_seconds", cooldown or DEFAULT_ALERT_COOLDOWN_SECONDS)
    )
    now_ts = int(time.time())

    with STATE_LOCK:
        state = _get_state()
        state_entry = state.get(action_key, {})
        last_started_ts = int(state_entry.get("started_ts", 0) or 0)

        if last_started_ts and now_ts - last_started_ts < cooldown:
            last_alert_ts = int(state_entry.get("last_alert_ts", 0) or 0)
            should_alert = (not last_alert_ts) or (
                alert_cooldown <= 0 or now_ts - last_alert_ts >= alert_cooldown
            )

            repeated = {
                "status": "alerted" if should_alert else "suppressed",
                "uid": runtime_cfg["uid"],
                "action_key": action_key,
                "appserver_type": appserver_type,
                "error_code": error_code,
                "last_started_at": state_entry.get("started_at", ""),
                "cooldown_seconds": cooldown,
                "alert_cooldown_seconds": alert_cooldown,
            }

            state_entry["last_repeat_at"] = _now_str()
            state_entry["last_repeat_ts"] = now_ts
            state_entry["last_repeat_payload"] = payload
            state[action_key] = state_entry

            if should_alert:
                state_entry["last_alert_at"] = _now_str()
                state_entry["last_alert_ts"] = now_ts
                state[action_key] = state_entry
                _save_state(state)
                _send_alert(runtime_cfg, action_key, action_cfg, state_entry, payload)
                classes.Err("midleo_actions alerted repeat for " + action_key)
            else:
                _save_state(state)
                classes.Err("midleo_actions suppressed repeat for " + action_key)

            return repeated

        start_info = _start_action(action_key, action_cfg, payload)
        state[action_key] = {
            "uid": runtime_cfg["uid"],
            "action_key": action_key,
            "appserver_type": appserver_type,
            "error_code": error_code,
            "script": start_info["script"],
            "args": start_info["args"],
            "pid": start_info["pid"],
            "started_at": start_info["started_at"],
            "started_ts": start_info["started_ts"],
            "last_alert_at": state_entry.get("last_alert_at", ""),
            "last_alert_ts": state_entry.get("last_alert_ts", 0),
            "last_payload": payload,
        }
        _save_state(state)

    classes.Err("midleo_actions started action " + action_key)
    return {
        "status": "started",
        "uid": runtime_cfg["uid"],
        "action_key": action_key,
        "appserver_type": appserver_type,
        "error_code": error_code,
        "script": start_info["script"],
        "pid": start_info["pid"],
        "started_at": start_info["started_at"],
    }


class ActionHandler(BaseHTTPRequestHandler):
    server_version = "MidleoActions/1.0"

    def log_message(self, format_string, *args):
        classes.Err("midleo_actions http " + (format_string % args))

    def _send_json(self, status_code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        remote_ip = str(self.client_address[0])
        if remote_ip not in ("127.0.0.1", "::1"):
            self._send_json(403, {"status": "error", "message": "localhost only"})
            return

        if self.path not in ("/", "/action"):
            self._send_json(404, {"status": "error", "message": "not found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0

        if content_length <= 0:
            self._send_json(400, {"status": "error", "message": "empty body"})
            return

        if content_length > MAX_BODY_BYTES:
            self._send_json(413, {"status": "error", "message": "body too large"})
            return

        try:
            raw_body = self.rfile.read(content_length)
            payload = json.loads(raw_body.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("json body must be an object")

            response = _handle_action(payload)
            self._send_json(200, response)
        except Exception as err:
            classes.Err("midleo_actions request error: " + str(err))
            self._send_json(400, {"status": "error", "message": str(err)})


def main():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT_NUMBER), ActionHandler)
    classes.Err("midleo_actions listening on " + HOST + ":" + str(PORT_NUMBER))
    server.serve_forever()


if __name__ == "__main__":
    main()
