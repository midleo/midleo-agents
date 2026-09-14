#!/usr/bin/env python3

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.base import classes, secrets

LOG_ENABLED = os.environ.get("MIDLEO_CRON_LOG", "").lower() in ("1", "true", "yes")
BASE_DIR = os.environ.get("MWAGTDIR", os.getcwd())
CONFIG_DIR = os.path.join(BASE_DIR, "config")
RUNABLE_DIR = os.path.join(BASE_DIR, "runable")

CRON_CONFIG_FILE = os.path.join(CONFIG_DIR, "cronjobs.json")
STATE_FILE = os.path.join(CONFIG_DIR, "cron_state.json")
NEXT_RUN_FILE = os.path.join(CONFIG_DIR, "nextrun.txt")
MAINTENANCE_FILE = os.path.join(CONFIG_DIR, "maintenance.flag")
try:
    DEFAULT_JOB_TIMEOUT_SECONDS = max(5, min(3600, int(os.environ.get("MIDLEO_JOB_TIMEOUT_SECONDS", "55"))))
except (TypeError, ValueError):
    DEFAULT_JOB_TIMEOUT_SECONDS = 55
MAX_CAPTURE_BYTES = 4000
SCRIPT_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+\.py$")
BLOCKED_CRON_SCRIPTS = {
    "addaction.py",
    "rmaction.py",
    "addcert.py",
    "delcert.py",
    "addappstat.py",
    "delappstat.py",
    "addoptadvisor.py",
    "deloptadvisor.py",
    "addmessagebackup.py",
    "rmmessbackup.py",
    "enableavl.py",
    "disableavl.py",
    "enabletrackqm.py",
    "disabletrackqm.py",
    "optadvisorctl.py",
    "setmaintenance.py",
    "startavl.py",
    "stopavl.py",
}


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message, level="DEBUG"):
    if LOG_ENABLED and level == "DEBUG":
        level = "INFO"
    classes.Log(message, level, "cron")


def read_json(path, default=None):
    if default is None:
        default = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else default
    except Exception:
        return default


def write_json_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def ensure_state_file():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.isfile(STATE_FILE):
        write_json_atomic(STATE_FILE, {})


def read_nextrun_ts():
    try:
        with open(NEXT_RUN_FILE, "r", encoding="utf-8") as f:
            value = f.read().strip()
            return int(value) if value else int(time.time())
    except Exception:
        return int(time.time())


def has_config_data(config_file):
    if not config_file:
        return True
    path = os.path.join(CONFIG_DIR, config_file)
    data = read_json(path, {})
    return isinstance(data, dict) and len(data) > 0


def rule_matches(rule, now_dt):
    if not isinstance(rule, dict):
        return False

    current_minute = now_dt.strftime("%M")
    current_hourminute = now_dt.strftime("%H%M")
    current_hour = now_dt.strftime("%H")

    if "minute_not_in" in rule:
        minutes = {str(x).zfill(2) for x in rule.get("minute_not_in", [])}
        if current_minute in minutes:
            return False

    if "hour_not_in" in rule:
        hours = {str(x).zfill(2) for x in rule.get("hour_not_in", [])}
        if current_hour in hours:
            return False

    if "hourminute_not_in" in rule:
        hourminutes = {str(x).zfill(4) for x in rule.get("hourminute_not_in", [])}
        if current_hourminute in hourminutes:
            return False

    if rule.get("always") is True:
        return True

    if "minute_in" in rule:
        minutes = {str(x).zfill(2) for x in rule.get("minute_in", [])}
        return current_minute in minutes

    if "hourminute" in rule:
        return current_hourminute == str(rule.get("hourminute")).zfill(4)

    if "minute" in rule:
        return current_minute == str(rule.get("minute")).zfill(2)

    if "hour" in rule:
        return current_hour == str(rule.get("hour")).zfill(2)

    return False


def resolve_args(args, context):
    return [str(item).format(**context) for item in (args or [])]


def safe_script_path(script_name):
    script_name = str(script_name or "")
    if (
        not SCRIPT_NAME_RE.fullmatch(script_name)
        or script_name != os.path.basename(script_name)
        or script_name in BLOCKED_CRON_SCRIPTS
    ):
        raise ValueError("invalid cron script name")
    script_path = os.path.realpath(os.path.join(RUNABLE_DIR, script_name))
    real_runable = os.path.realpath(RUNABLE_DIR)
    try:
        if os.path.commonpath([real_runable, script_path]) != real_runable:
            raise ValueError("cron script outside runable directory")
    except ValueError:
        raise ValueError("cron script outside runable directory")
    return script_path


def should_run_job(script_name, job, now_ts, now_dt, nextrun_ts):
    if not isinstance(job, dict):
        log(f"{script_name} skipped invalid_job_definition")
        return False

    if not job.get("enabled", False):
        log(f"{script_name} skipped disabled")
        return False

    try:
        safe_script_path(script_name)
    except ValueError as err:
        log(f"{script_name} skipped {err}")
        return False

    if not rule_matches(job.get("run", {}), now_dt):
        log(f"{script_name} skipped schedule_no_match")
        return False

    if not has_config_data(job.get("config_file")):
        log(f"{script_name} skipped empty_config_file={job.get('config_file', '')}")
        return False

    if job.get("skip_if_maintenance", False) and os.path.isfile(MAINTENANCE_FILE):
        log(f"{script_name} skipped maintenance")
        return False

    if job.get("requires_nextrun_check", False) and nextrun_ts > now_ts:
        log(f"{script_name} skipped nextrun_wait")
        return False

    env_name = job.get("requires_exec_env")
    if env_name:
        env_value = os.environ.get(env_name, "")
        if (
            not env_value
            or not os.path.isfile(env_value)
            or not os.access(env_value, os.X_OK)
        ):
            log(f"{script_name} skipped invalid_env_exec={env_name}")
            return False

    return True


def _terminate_job_tree(process):
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        elif os.name == "nt":
            taskkill = shutil.which("taskkill.exe")
            if taskkill:
                subprocess.run([taskkill, "/PID", str(process.pid), "/T", "/F"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, shell=False, timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=1)
    except (OSError, subprocess.SubprocessError):
        log("Unable to confirm timeout cleanup for job pid=" + str(process.pid), "WARNING")


def _capture_job(command, timeout_seconds):
    tails = [bytearray(), bytearray()]
    process = subprocess.Popen(command, cwd=BASE_DIR, env=os.environ.copy(),
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, shell=False,
                               start_new_session=(os.name == "posix"))

    def drain(stream, tail):
        try:
            while True:
                chunk = os.read(stream.fileno(), 8192)
                if not chunk:
                    break
                tail.extend(chunk)
                if len(tail) > MAX_CAPTURE_BYTES:
                    del tail[:-MAX_CAPTURE_BYTES]
        except (OSError, ValueError):
            pass

    streams = (process.stdout, process.stderr)
    readers = [threading.Thread(target=drain, args=(stream, tail), daemon=True)
               for stream, tail in zip(streams, tails)]
    for reader in readers:
        reader.start()
    timed_out = False
    try:
        code = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_job_tree(process)
        code = 124
    finally:
        for reader in readers:
            reader.join(timeout=1)
        for stream in streams:
            stream.close()
    stdout, stderr = [secrets.redact_text(bytes(tail).decode("utf-8", errors="replace")) for tail in tails]
    if timed_out:
        stderr = "job timed out after " + str(timeout_seconds) + " seconds"
    return code, stdout, stderr


def run_job(script_name, args, job=None):
    python_bin = os.environ.get("PYTHON") or sys.executable
    try:
        script_path = safe_script_path(script_name)
    except ValueError as err:
        return {
            "last_run_ts": int(time.time()),
            "last_run": now_str(),
            "finished_ts": int(time.time()),
            "finished_at": now_str(),
            "exit_code": 998,
            "args": args,
            "error": str(err),
        }

    if not os.path.isfile(script_path):
        return {
            "last_run_ts": int(time.time()),
            "last_run": now_str(),
            "finished_ts": int(time.time()),
            "finished_at": now_str(),
            "exit_code": 999,
            "args": args,
            "error": f"script_not_found:{script_path}",
        }

    started_ts = int(time.time())
    started_at = now_str()

    timeout_seconds = DEFAULT_JOB_TIMEOUT_SECONDS
    if isinstance(job, dict) and job.get("timeout_seconds") is not None:
        try:
            timeout_seconds = int(job.get("timeout_seconds"))
        except Exception:
            pass
    try:
        timeout_seconds = int(os.environ.get("JOB_TIMEOUT_SECONDS", timeout_seconds))
    except Exception:
        pass
    timeout_seconds = max(5, min(timeout_seconds, 3600))

    try:
        exit_code, stdout, stderr = _capture_job([python_bin, script_path] + list(args), timeout_seconds)
    except OSError as err:
        exit_code, stdout, stderr = 127, "", secrets.redact_text(str(err))

    ended_ts = int(time.time())
    ended_at = now_str()

    return {
        "last_run_ts": started_ts,
        "last_run": started_at,
        "finished_ts": ended_ts,
        "finished_at": ended_at,
        "exit_code": exit_code,
        "args": args,
        "stdout": stdout,
        "stderr": stderr,
    }


def main():
    if not os.path.isfile(CRON_CONFIG_FILE):
        log("cronjobs skipped missing config/cronjobs.json")
        return 0

    ensure_state_file()

    cron_config = read_json(CRON_CONFIG_FILE, {})
    state = read_json(STATE_FILE, {})

    now_dt = datetime.now()
    now_ts = int(time.time())
    cron_started_ts = now_ts
    cron_started_at = now_str()
    nextrun_ts = read_nextrun_ts()

    context = {
        "YM": now_dt.strftime("%Y-%m"),
        "WD": now_dt.strftime("%d"),
        "HOUR": now_dt.strftime("%H%M"),
        "CM": now_dt.strftime("%M"),
        "NOW_TS": str(now_ts),
        "TST": str(nextrun_ts),
    }

    failed = False
    ran_any = False
    ran_jobs = 0
    failed_jobs = 0

    for script_name, job in cron_config.items():
        if not should_run_job(script_name, job, now_ts, now_dt, nextrun_ts):
            continue

        args = resolve_args(job.get("args", []), context)
        log(f"{script_name} start args={args}")
        result = run_job(script_name, args, job)
        state[script_name] = result
        write_json_atomic(STATE_FILE, state)

        if result.get("exit_code", 1) == 0:
            log(f"{script_name} ok")
        else:
            log(f"{script_name} failed exit_code={result.get('exit_code')} error={result.get('stderr', result.get('error', ''))}", "ERROR")

        ran_any = True
        ran_jobs += 1

        if result["exit_code"] != 0 and not job.get("ignore_error", False):
            failed = True
            failed_jobs += 1

    if not ran_any:
        log("cronjobs no_jobs_ran")

    exit_code = 1 if failed else 0
    state["_meta"] = {
        "last_execution_started_ts": cron_started_ts,
        "last_execution_started_at": cron_started_at,
        "last_execution_finished_ts": int(time.time()),
        "last_execution_finished_at": now_str(),
        "last_execution_exit_code": exit_code,
        "last_ran_jobs": ran_jobs,
        "last_failed_jobs": failed_jobs,
    }
    write_json_atomic(STATE_FILE, state)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
