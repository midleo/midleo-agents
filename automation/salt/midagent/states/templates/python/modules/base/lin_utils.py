import datetime
import multiprocessing
import platform
import re
import socket
import subprocess
import sys

try:
    import psutil
except Exception as PSUTIL_IMPORT_ERROR:
    psutil = None

from modules.base import classes


def _log_error(err, function_name):
    classes.Err("Exception:" + str(err) + " at " + function_name + "()")


def _psutil_available(function_name):
    if psutil is not None:
        return True
    classes.Err("Exception:psutil is not available:" + str(PSUTIL_IMPORT_ERROR) + " at " + function_name + "()")
    return False


def _namedtuple_to_dict(value):
    return {field: getattr(value, field) for field in getattr(value, "_fields", ())}


def _addr_to_dict(addr):
    if not addr:
        return {}
    if hasattr(addr, "_fields"):
        return _namedtuple_to_dict(addr)
    if isinstance(addr, tuple):
        return {
            "ip": addr[0] if len(addr) > 0 else "",
            "port": addr[1] if len(addr) > 1 else "",
        }
    return {"addr": str(addr)}


def _link_families():
    families = set()
    if psutil is not None and hasattr(psutil, "AF_LINK"):
        families.add(psutil.AF_LINK)
    if hasattr(socket, "AF_PACKET"):
        families.add(socket.AF_PACKET)
    families.add(-1)
    return families

def getName():
    try:
        return socket.getfqdn()
    except Exception as err:
        _log_error(err, "getName")
        return None

def getArchitecture():
    try:
        return platform.architecture(sys.executable, '', '')[0]
    except Exception as err:
        _log_error(err, "getArchitecture")
        return None

def getCPUName():
    try:
        all_info = subprocess.check_output(
            ["lscpu"], stderr=subprocess.DEVNULL, timeout=10
        ).decode("utf-8", errors="ignore")
        for line in all_info.splitlines():
            if "Model name" in line:
                return re.sub(r".*Model name.*:", "", line, 1).strip()
    except Exception as err:
        _log_error(err, "getCPUName")
    return platform.processor() or None

def getCPUCoreCount():
    try:
        return multiprocessing.cpu_count()
    except Exception as err:
        _log_error(err, "getCPUCoreCount")
        return 0

def getMachineType():
    try:
        return platform.machine()
    except Exception as err:
        _log_error(err, "getMachineType")
        return None

def getOS():
    try:
        return platform.system()+ " " +platform.release()
    except Exception as err:
        _log_error(err, "getOS")
        return {}

def getMemory():
    try:
        if not _psutil_available("getMemory"):
            return {}
        return _namedtuple_to_dict(psutil.virtual_memory())
    except Exception as err:
        _log_error(err, "getMemory")
        return {}

def getDiskPartitions():
    try:
        if not _psutil_available("getDiskPartitions"):
            return []
        partitions = []
        for disk in psutil.disk_partitions(all=True):
            partition = _namedtuple_to_dict(disk)
            try:
                disk_usage = _namedtuple_to_dict(psutil.disk_usage(disk.mountpoint))
            except Exception:
                disk_usage = {}
            partition['disk_usage'] = disk_usage
            partitions.append(partition)
        return partitions
    except Exception as err:
        _log_error(err, "getDiskPartitions")
        return []

def getLBTS():
    try:
        if not _psutil_available("getLBTS"):
            return 0
        return datetime.datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
    except Exception as err:
        _log_error(err, "getLBTS")
        return 0

def getIP():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        finally:
            sock.close()
    except Exception:
        pass
    try:
        hostname = socket.gethostname()
        return socket.gethostbyname(hostname)
    except Exception as err:
        _log_error(err, "getIP")
        return 0

def getConnections():
    try:
        if not _psutil_available("getConnections"):
            return []
        connections = []
        for conn in psutil.net_connections(kind="inet"):
            if not conn.status:
                continue
            connection = _namedtuple_to_dict(conn)
            connection["laddr"] = _addr_to_dict(conn.laddr)
            connection["raddr"] = _addr_to_dict(conn.raddr)
            connections.append(connection)
        return connections
    except Exception as err:
        _log_error(err, "getConnections")
        return []

def getIFAddresses():
    try:
        if not _psutil_available("getIFAddresses"):
            return []
        interfaces = []
        link_families = _link_families()
        for net, addr in psutil.net_if_addrs().items():
            interface = {
                'name': False,
                'MAC': {
                    'addr': False,
                    'netmask': False
                },
                'IPv4': {
                    'addr': False,
                    'netmask': False
                },
                'IPv6': {
                    'addr': False,
                    'netmask': False
                }
            }
            interface['name'] = net
            for x in addr: 
                if x.family in link_families:
                    interface['MAC']['addr'] = x.address
                    interface['MAC']['netmask'] = x.netmask
                elif x.family == socket.AF_INET:
                    interface['IPv4']['addr'] = x.address
                    interface['IPv4']['netmask'] = x.netmask
                elif x.family == socket.AF_INET6:
                    interface['IPv6']['addr'] = x.address
                    interface['IPv6']['netmask'] = x.netmask
            interfaces.append(interface)
        return interfaces
    except Exception as err:
        _log_error(err, "getIFAddresses")
        return []
