import sys
import os
import inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import configs

QMGR = sys.argv[1]


def createTrackJson():
    track_data = configs.gettrackData()
    track_data[QMGR] = {
        "type": "enabled"
    }
    configs.savetrackData(track_data)
    print(QMGR + " have been added")


if __name__ == "__main__":
    createTrackJson()