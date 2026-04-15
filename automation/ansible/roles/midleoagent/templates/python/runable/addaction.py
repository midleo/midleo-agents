import json
import sys
import os
import inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import configs


def _load_input():
    if len(sys.argv) < 2:
        raise ValueError("Missing action definition")

    if len(sys.argv) == 2:
        payload = json.loads(sys.argv[1])
        if not isinstance(payload, dict):
            raise ValueError("Action payload must be a JSON object")

        action_key = str(payload.get("action_key", "")).strip()
        if not action_key:
            raise ValueError("action_key is required")

        action_body = dict(payload)
        action_body.pop("action_key", None)
        return action_key, action_body

    action_key = str(sys.argv[1]).strip()
    action_body = json.loads(sys.argv[2])
    if not action_key:
        raise ValueError("action key is required")
    if not isinstance(action_body, dict):
        raise ValueError("Action configuration must be a JSON object")
    return action_key, action_body


def _validate_action(action_key, action_body):
    if "." not in action_key:
        raise ValueError("action key must look like appserver_type.error_code")

    script_path = str(action_body.get("script", "")).strip()
    if not script_path:
        raise ValueError("script is required")

    args = action_body.get("args", [])
    if "args" in action_body and not isinstance(args, list):
        raise ValueError("args must be a JSON array")


def add_action():
    action_key, action_body = _load_input()
    _validate_action(action_key, action_body)

    action_data = configs.getActionData()
    action_data[action_key] = action_body
    configs.saveActionData(action_data)
    print("Action " + action_key + " saved")


if __name__ == "__main__":
    add_action()
