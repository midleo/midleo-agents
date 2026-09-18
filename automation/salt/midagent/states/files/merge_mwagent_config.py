#!/usr/bin/env python3
import os
import sys


_SKIP_EMPTY = frozenset(
    ("SRVUID", "INTTOKEN", "GROUPID", "MWADMIN", "SSLENABLED", "PYTHON")
)


def _parse_keys(text):
    keys = {}
    order = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key or key in keys:
            continue
        keys[key] = value
        order.append(key)
    return keys, order


def merge_missing(existing_text, desired_text):
    newline = "\r\n" if "\r\n" in existing_text else "\n"
    existing, _ = _parse_keys(existing_text)
    desired, desired_order = _parse_keys(desired_text)
    additions = []
    for key in desired_order:
        if key in existing:
            continue
        value = desired.get(key, "")
        if key in _SKIP_EMPTY and not value.strip().strip("'\""):
            continue
        additions.append(key + "=" + value)
    if not additions:
        return existing_text, []
    out = existing_text
    if out and not out.endswith(("\n", "\r\n")):
        out += newline
    out += newline.join(additions) + newline
    return out, additions


def merge_files(existing_path, desired_path):
    with open(existing_path, "r", encoding="utf-8") as stream:
        existing_text = stream.read()
    with open(desired_path, "r", encoding="utf-8") as stream:
        desired_text = stream.read()
    merged, additions = merge_missing(existing_text, desired_text)
    if additions:
        temp_path = existing_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8", newline="") as stream:
            stream.write(merged)
        os.replace(temp_path, existing_path)
    return additions


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: merge_mwagent_config.py EXISTING DESIRED\n")
        return 2
    additions = merge_files(argv[1], argv[2])
    if additions:
        sys.stdout.write("added " + ",".join(item.split("=", 1)[0] for item in additions) + "\n")
    else:
        sys.stdout.write("no missing keys\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
