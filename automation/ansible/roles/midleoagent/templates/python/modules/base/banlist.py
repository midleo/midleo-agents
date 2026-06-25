import ipaddress
import json
from pathlib import Path

_DEFAULT_BANNED = {
    "ips": [
        "10.255.255.254",
    ],
}


def _banned_path():
    return Path.cwd() / "config" / "banned.json"


def _peer_host(peername):
    if not peername:
        return ""
    return str(peername[0] if isinstance(peername, (tuple, list)) else peername).strip()


def _peer_ip(peername):
    host = _peer_host(peername)
    if not host:
        return None
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def ensure_banned_file():
    path = _banned_path()
    if path.is_file():
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(_DEFAULT_BANNED, indent=2) + "\n",
            encoding="utf-8",
        )
        try:
            path.chmod(0o600)
        except OSError:
            pass
    except OSError:
        pass


def _load_banned_data():
    ensure_banned_file()
    path = _banned_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _load_ip_entries():
    data = _load_banned_data()
    ips = data.get("ips", [])
    if not isinstance(ips, list):
        return []
    return ips


def _parse_ban_entry(entry):
    text = str(entry).strip()
    if not text:
        return None
    try:
        if "/" in text:
            return ipaddress.ip_network(text, strict=False)
        return ipaddress.ip_address(text)
    except ValueError:
        return None


def is_banned(peername):
    addr = _peer_ip(peername)
    if addr is None:
        return False

    for entry in _load_ip_entries():
        parsed = _parse_ban_entry(entry)
        if parsed is None:
            continue
        if isinstance(parsed, (ipaddress.IPv4Network, ipaddress.IPv6Network)):
            if addr in parsed:
                return True
        elif addr == parsed:
            return True
    return False


def add_banned(peername, reason=""):
    addr = _peer_ip(peername)
    if addr is None:
        return False
    if is_banned(str(addr)):
        return False

    path = _banned_path()
    data = _load_banned_data()
    ips = data.get("ips", [])
    if not isinstance(ips, list):
        ips = []
    ip_text = str(addr)
    if ip_text in [str(item).strip() for item in ips]:
        return False

    ips.append(ip_text)
    data["ips"] = ips
    if reason:
        data["last_reason"] = str(reason)[:200]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(path.name + ".tmp")
        tmp_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        tmp_path.replace(path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return True
    except OSError:
        return False
