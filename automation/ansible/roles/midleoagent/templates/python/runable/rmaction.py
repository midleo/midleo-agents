import sys
import os
import inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import configs


def remove_action():
    if len(sys.argv) < 2:
        raise ValueError("Missing action key")

    action_key = str(sys.argv[1]).strip()
    if not action_key:
        raise ValueError("action key is required")

    action_data = configs.getActionData()
    action_data.pop(action_key, None)
    configs.saveActionData(action_data)
    print("Action " + action_key + " removed")


if __name__ == "__main__":
    remove_action()
