import inspect
import json
import os
import sys

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.statistics import common
from modules.base import configs, makerequest


def _print_state(state):
    output = {
        "status": state.get("status"),
        "active": bool(state.get("active")),
        "enabled": bool(state.get("enabled")),
        "enabled_at": state.get("enabled_at"),
        "expires_at": state.get("expires_at"),
        "disabled_at": state.get("disabled_at"),
        "max_days": state.get("max_days", common.MAX_OPTADVISOR_ENABLE_DAYS),
        "requested_days": state.get("requested_days"),
    }
    if "collector_tokens" in state:
        output["collector_tokens"] = state["collector_tokens"]
    print(json.dumps(output, sort_keys=True))


def _usage():
    print("usage: optadvisorctl.py enable [days]|disable [reason]|status")
    return 1


def _response_json(response):
    if response is None:
        return {}
    try:
        return response.json()
    except Exception:
        try:
            return json.loads(response.text or "{}")
        except Exception:
            return {}


def _provision_collector_tokens(days):
    cfg = configs.getcfgData()
    website = cfg.get("MWADMIN", "")
    webssl = cfg.get("SSLENABLED", "n")
    inttoken = cfg.get("INTTOKEN", "")
    result = {"configured": 0, "provisioned": 0, "failed": 0}
    if not website or not inttoken:
        result["failed"] = 1
        result["error"] = "missing MWADMIN or INTTOKEN"
        return result

    opt_data = configs.getOptAdvisorData()
    changed = False
    try:
        expires_days = max(1, min(int(days), common.MAX_OPTADVISOR_ENABLE_DAYS))
    except Exception:
        expires_days = common.MAX_OPTADVISOR_ENABLE_DAYS

    for srvtype, servers in list(opt_data.items()):
        if not isinstance(servers, dict):
            continue
        for appsrv, item in list(servers.items()):
            if not isinstance(item, dict):
                continue
            opt_config, _ = common.split_optadvisor_config(item)
            if not common.optadvisor_enabled(opt_config):
                continue
            result["configured"] += 1
            appcode = common.safe_text(opt_config.get("appcode"))
            server_id = common.safe_text(
                opt_config.get("server_id")
                or opt_config.get("appsrvid")
                or opt_config.get("srvid")
                or opt_config.get("serverid")
            )
            technology = common.safe_text(opt_config.get("optadvisor_technology") or srvtype)
            if not technology:
                result["failed"] += 1
                continue

            payload = {
                "technology": technology,
                "expires_days": expires_days,
                "server_name": appsrv,
                "appsrv": appsrv,
            }
            if appcode:
                payload["appcode"] = appcode
            if server_id:
                payload["server_id"] = server_id
                payload["appsrvid"] = server_id

            response = makerequest.postOptAdvisorCollectorToken(webssl, website, payload, inttoken)
            data = _response_json(response)
            if response is None or response.status_code < 200 or response.status_code >= 300 or not data.get("collector_token"):
                result["failed"] += 1
                continue

            item["optadvisor_token"] = data["collector_token"]
            item["optadvisor_token_uid"] = data.get("token_uid", "")
            item["optadvisor_token_expires_at"] = data.get("expires_at", "")
            item["appcode"] = data.get("appcode", item.get("appcode", ""))
            item["server_id"] = data.get("server_id", data.get("srvid", item.get("server_id", item.get("appsrvid", ""))))
            item["appsrvid"] = data.get("srvid", item.get("appsrvid", item["server_id"]))
            item["srvid"] = data.get("srvid", item.get("srvid", ""))
            item["serverid"] = data.get("serverid", item.get("serverid", ""))
            item["optadvisor_technology"] = data.get("technology", item.get("optadvisor_technology", technology))
            result["provisioned"] += 1
            changed = True

    if changed:
        configs.saveOptAdvisorData(opt_data)
    return result


def main(argv):
    action = argv[1].lower() if len(argv) > 1 else "status"
    if action == "enable":
        days = argv[2] if len(argv) > 2 else common.MAX_OPTADVISOR_ENABLE_DAYS
        common.enable_optadvisor_runtime(days=days, actor=os.environ.get("USER", "manual"))
        state = common.optadvisor_runtime_status()
        token_state = _provision_collector_tokens(days)
        state["collector_tokens"] = token_state
        _print_state(state)
        return 2 if token_state.get("configured", 0) > 0 and token_state.get("failed", 0) > 0 else 0
    if action == "disable":
        reason = " ".join(argv[2:]) if len(argv) > 2 else "manual"
        common.disable_optadvisor_runtime(actor=os.environ.get("USER", "manual"), reason=reason)
        _print_state(common.optadvisor_runtime_status())
        return 0
    if action == "status":
        _print_state(common.optadvisor_runtime_status())
        return 0
    return _usage()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
