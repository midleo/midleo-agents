#!/usr/bin/env python3
"""Notify Midleo Core that this agent host is being removed (mark inactive, keep data)."""

import inspect
import os
import sys

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import classes, configs, makerequest

def main():
    cfg = configs.getcfgData() or {}
    uid = str(cfg.get("SRVUID", "")).strip()
    website = str(cfg.get("MWADMIN", "")).strip()
    webssl = str(cfg.get("SSLENABLED", "y")).strip()
    if not uid or not website:
        classes.Err("deactivate_server: SRVUID or MWADMIN missing")
        return 1
    ok = makerequest.postDeactivateServer(
        webssl,
        website,
        {"uid": uid, "reason": "agent_removed"},
    )
    if not ok:
        classes.Err("deactivate_server: Core did not accept deactivate for " + uid)
        return 2
    classes.Log("Server marked inactive in Midleo Core: " + uid, component="remove")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
