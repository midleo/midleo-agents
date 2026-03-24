#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import time
from datetime import datetime

LOG_ENABLED = False
BASE_DIR = os.environ.get("MWAGTDIR", os.getcwd())
CONFIG_DIR = os.path.join(BASE_DIR, "config")
RUNABLE_DIR = os.path.join(BASE_DIR, "runable")

CRON_CONFIG_FILE = os.path.join(CONFIG_DIR, "cronjobs.json")
STATE_FILE = os.path.join(CONFIG_DIR, "cron_state.json")
NEXT_RUN_FILE = os.path.join(CONFIG_DIR, "nextrun.txt")
MAINTENANCE_FILE = os.path.join(CONFIG_DIR, "maintenance.flag")
LOG_FILE = os.path.join(CONFIG_DIR, "cronjobs.log")


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message):
    if not LOG_ENABLED:
        return
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{now_str()} {message}\n")


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


def should_run_job(script_name, job, now_ts, now_dt, nextrun_ts):
    if not isinstance(job, dict):
        log(f"{script_name} skipped invalid_job_definition")
        return False

    if not job.get("enabled", False):
        log(f"{script_name} skipped disabled")
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

    if not rule_matches(job.get("run", {}), now_dt):
        log(f"{script_name} skipped schedule_no_match")
        return False

    return True


def run_job(script_name, args):
    python_bin = os.environ["PYTHON"]
    script_path = os.path.join(RUNABLE_DIR, script_name)

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

    completed = subprocess.run(
        [python_bin, script_path, *args],
        cwd=BASE_DIR,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )

    ended_ts = int(time.time())
    ended_at = now_str()

    return {
        "last_run_ts": started_ts,
        "last_run": started_at,
        "finished_ts": ended_ts,
        "finished_at": ended_at,
        "exit_code": completed.returncode,
        "args": args,
        "stdout": completed.stdout[-4000:] if completed.stdout else "",
        "stderr": completed.stderr[-4000:] if completed.stderr else "",
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

    for script_name, job in cron_config.items():
        if not should_run_job(script_name, job, now_ts, now_dt, nextrun_ts):
            continue

        args = resolve_args(job.get("args", []), context)
        log(f"{script_name} start args={args}")
        result = run_job(script_name, args)
        state[script_name] = result
        write_json_atomic(STATE_FILE, state)

        if result.get("exit_code", 1) == 0:
            log(f"{script_name} ok")
        else:
            log(f"{script_name} failed exit_code={result.get('exit_code')}")

        ran_any = True

        if result["exit_code"] != 0 and not job.get("ignore_error", False):
            failed = True

    if not ran_any:
        log("cronjobs no_jobs_ran")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
