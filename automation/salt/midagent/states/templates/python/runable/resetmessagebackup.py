import inspect
import os
import sys

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import classes, configs
from modules.message_backup.outbox import MessageBackupOutbox

try:
    config_data = configs.getMessageBackupData()
    root = config_data.get("message_backup") if isinstance(config_data.get("message_backup"), dict) else config_data
    if not root or not root.get("enabled", True):
        raise SystemExit(0)
    outbox = MessageBackupOutbox(root.get("outbox") or {})
    cfg = configs.getcfgData() or {}
    from modules.message_backup import scheduler

    scheduler.flush_outbox(root, outbox)
    classes.Err("resetmessagebackup flushed outbox size=" + str(outbox.size()))
except Exception as err:
    classes.Err("resetmessagebackup error:" + str(err))
