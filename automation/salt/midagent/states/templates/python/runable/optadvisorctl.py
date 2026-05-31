import inspect
import json
import os
import sys

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.statistics import common
from modules.base import configs


REMOVED_OPTADVISOR_AUTH_KEYS = {
    "optadvisor_token",
    "optadvisor_token_uid",
    "optadvisor_token_expires_at",
    "collector_token",
}


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
    if state.get("removed_token_fields"):
        output["removed_token_fields"] = int(state.get("removed_token_fields", 0))
    print(json.dumps(output, sort_keys=True))


def _usage():
    print("usage: optadvisorctl.py enable [days]|disable [reason]|status")
    return 1


def _remove_removed_token_fields():
    opt_data = configs.getOptAdvisorData()
    changed = False
    removed = 0
    for servers in opt_data.values():
        if not isinstance(servers, dict):
            continue
        for item in servers.values():
            if not isinstance(item, dict):
                continue
            for key in REMOVED_OPTADVISOR_AUTH_KEYS:
                if key in item:
                    item.pop(key, None)
                    removed += 1
                    changed = True
    if changed:
        configs.saveOptAdvisorData(opt_data)
    return removed


def main(argv):
    action = argv[1].lower() if len(argv) > 1 else "status"
    if action == "enable":
        days = argv[2] if len(argv) > 2 else common.MAX_OPTADVISOR_ENABLE_DAYS
        removed = _remove_removed_token_fields()
        common.enable_optadvisor_runtime(days=days, actor=os.environ.get("USER", "manual"))
        state = common.optadvisor_runtime_status()
        if removed:
            state["removed_token_fields"] = removed
        _print_state(state)
        return 0
    if action == "disable":
        reason = " ".join(argv[2:]) if len(argv) > 2 else "manual"
        common.disable_optadvisor_runtime(actor=os.environ.get("USER", "manual"), reason=reason)
        _print_state(common.optadvisor_runtime_status())
        return 0
    if action == "status":
        removed = _remove_removed_token_fields()
        state = common.optadvisor_runtime_status()
        if removed:
            state["removed_token_fields"] = removed
        _print_state(state)
        return 0
    return _usage()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
