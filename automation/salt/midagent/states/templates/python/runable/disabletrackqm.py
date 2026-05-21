import sys
import os
import inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import configs


def _arg(index, name):
    try:
        value = sys.argv[index]
    except IndexError:
        raise ValueError("Missing required argument: " + name)
    value = str(value).strip()
    if not value:
        raise ValueError("Empty required argument: " + name)
    return value


def disableTrackQm():
    qmgr = _arg(1, "QMGR")
    track_data = configs.gettrackData()
    track_data.pop(qmgr, None)
    configs.savetrackData(track_data)
    print(qmgr + " configuration deleted")


if __name__ == "__main__":
    disableTrackQm()
