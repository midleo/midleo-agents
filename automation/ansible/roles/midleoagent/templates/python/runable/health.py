import glob
import json
import os
import stat
import sys
import time
from datetime import datetime, timezone

currentdir = os.path.dirname(os.path.abspath(__file__))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import configs

BASE_DIR = os.getcwd()
CONFIG_DIR = os.path.join(BASE_DIR, "config")
LOG_DIR = os.path.join(BASE_DIR, "logs")
CRON_STATE_FILE = os.path.join(CONFIG_DIR, "cron_state.json")
PYTHON_PACKAGES = (
    "psutil",
    "py-cpuinfo",
    "dnspython",
    "requests",
    "pycryptodome",
    "pywinrm",
    "netifaces",
    "pymqi",
)


def _iso_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _agent_version():
    try:
        with open(os.path.join(parentdir, "midleo_client.py"), "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("AGENT_VER"):
                    return line.split("=", 1)[1].strip().strip("\"'")
    except Exception:
        pass
    return "unknown"


def _mode(path):
    try:
        return stat.S_IMODE(os.stat(path).st_mode)
    except Exception:
        return None


def _mode_text(mode):
    return "" if mode is None else oct(mode)


def _count_lines(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0


def _file_size(path):
    try:
        return os.path.getsize(path)
    except Exception:
        return 0


def _installed_version(package_name):
    try:
        from importlib import metadata
        return metadata.version(package_name)
    except Exception:
        return ""


def _dependency_status():
    packages = []
    missing = 0
    for name in PYTHON_PACKAGES:
        installed = _installed_version(name)
        if not installed and name != "pymqi":
            missing += 1
        packages.append({"name": name, "installed": installed, "optional": name == "pymqi"})
    return {
        "checked": len(packages),
        "missing_required": missing,
        "packages": packages,
    }


def _cron_status():
    state = _read_json(CRON_STATE_FILE)
    meta = state.get("_meta") if isinstance(state.get("_meta"), dict) else {}
    jobs = {}
    failed_jobs = 0
    for name, item in state.items():
        if str(name).startswith("_") or not isinstance(item, dict):
            continue
        exit_code = item.get("exit_code")
        if exit_code not in (None, "", 0):
            failed_jobs += 1
        jobs[name] = {
            "last_run": item.get("last_run"),
            "finished_at": item.get("finished_at"),
            "exit_code": exit_code,
        }
    return {
        "last_execution_started_at": meta.get("last_execution_started_at"),
        "last_execution_finished_at": meta.get("last_execution_finished_at"),
        "last_execution_exit_code": meta.get("last_execution_exit_code"),
        "last_ran_jobs": meta.get("last_ran_jobs", 0),
        "last_failed_jobs": meta.get("last_failed_jobs", failed_jobs),
        "jobs": jobs,
    }


def _upload_status():
    state = configs.getUploadState()
    if not isinstance(state, dict):
        state = {}
    return {
        "last_success_at": state.get("last_success_at"),
        "last_success_path": state.get("last_success_path"),
        "last_failure_at": state.get("last_failure_at"),
        "last_failure_path": state.get("last_failure_path"),
        "last_failure_status_code": state.get("last_failure_status_code"),
        "success_count": int(state.get("success_count", 0)),
        "failure_count": int(state.get("failure_count", 0)),
        "consecutive_failures": int(state.get("consecutive_failures", 0)),
        "total_attempts": int(state.get("total_attempts", 0)),
    }


def _backlog_status():
    optadvisor_files = []
    optadvisor_lines = 0
    for path in sorted(glob.glob(os.path.join(LOG_DIR, "*_optadvisor.jsonl"))):
        lines = _count_lines(path)
        optadvisor_lines += lines
        optadvisor_files.append(
            {
                "file": os.path.basename(path),
                "lines": lines,
                "bytes": _file_size(path),
            }
        )
    local_stat_files = []
    for pattern in ("Statistics_*.csv", "ResourceStats_*.txt", "avl_*.csv"):
        local_stat_files.extend(glob.glob(os.path.join(LOG_DIR, pattern)))
    return {
        "optadvisor_files": len(optadvisor_files),
        "optadvisor_events": optadvisor_lines,
        "optadvisor": optadvisor_files,
        "local_stat_files": len(set(local_stat_files)),
        "local_stat_bytes": sum(_file_size(path) for path in set(local_stat_files)),
    }


def _permission_status():
    checks = []
    for path, max_mode in (
        (CONFIG_DIR, 0o700),
        (LOG_DIR, 0o700),
        (os.path.join(CONFIG_DIR, "mwagent.config"), 0o600),
        (os.path.join(CONFIG_DIR, "agent.identity"), 0o600),
        (os.path.join(CONFIG_DIR, "cron_state.json"), 0o600),
        (os.path.join(CONFIG_DIR, "upload_state.json"), 0o600),
    ):
        if not os.path.exists(path):
            continue
        mode = _mode(path)
        ok = mode is not None and (mode & 0o077) == 0 and mode <= max_mode
        checks.append({"path": os.path.relpath(path, BASE_DIR), "mode": _mode_text(mode), "ok": ok})
    insecure = sum(1 for item in checks if not item["ok"])
    return {"checked": len(checks), "insecure": insecure, "items": checks}


def main():
    cron = _cron_status()
    upload = _upload_status()
    backlog = _backlog_status()
    deps = _dependency_status()
    perms = _permission_status()

    issues = []
    if upload["consecutive_failures"] > 0:
        issues.append("upload_failures")
    if cron.get("last_execution_exit_code") not in (None, "", 0):
        issues.append("cron_failure")
    if deps["missing_required"] > 0:
        issues.append("missing_dependencies")
    if perms["insecure"] > 0:
        issues.append("insecure_permissions")

    payload = {
        "status": "ok" if not issues else "degraded",
        "issues": issues,
        "generated_at": _iso_now(),
        "generated_ts": int(time.time()),
        "agent_version": _agent_version(),
        "cron": cron,
        "uploads": upload,
        "backlog": backlog,
        "dependencies": deps,
        "permissions": perms,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
