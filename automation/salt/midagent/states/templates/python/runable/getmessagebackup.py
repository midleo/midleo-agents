import inspect
import os
import sys

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import classes
from modules.message_backup import scheduler

try:
    scheduler.run_once()
except Exception as err:
    classes.Err("getmessagebackup error:" + str(err))
