import platform, sys, psutil, socket, datetime, winreg
from modules.base import appsrv_catalog, classes


def _registry_value(key, name):
    try:
        value, _value_type = winreg.QueryValueEx(key, name)
        return str(value or "").strip()
    except Exception:
        return ""


def getInstalledSW(hive, flag):
    software_list = []
    registry = None
    uninstall_key = None
    try:
        registry = winreg.ConnectRegistry(None, hive)
        uninstall_key = winreg.OpenKey(
            registry,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            0,
            winreg.KEY_READ | flag,
        )
        count_subkey = winreg.QueryInfoKey(uninstall_key)[0]

        for index in range(count_subkey):
            subkey = None
            try:
                subkey_name = winreg.EnumKey(uninstall_key, index)
                subkey = winreg.OpenKey(uninstall_key, subkey_name)
                name = _registry_value(subkey, "DisplayName")
                if not name:
                    continue
                publisher = _registry_value(subkey, "Publisher")
                if (
                    not appsrv_catalog.match_package_name(name)
                    and not appsrv_catalog.match_windows_display_name(name, publisher)
                ):
                    continue
                software_list.append(
                    {
                        "name": name,
                        "version": _registry_value(subkey, "DisplayVersion"),
                        "publisher": publisher,
                        "install_location": _registry_value(subkey, "InstallLocation"),
                        "description": "",
                    }
                )
            except Exception:
                continue
            finally:
                if subkey is not None:
                    try:
                        winreg.CloseKey(subkey)
                    except Exception:
                        pass
    except Exception:
        return None
    finally:
        if uninstall_key is not None:
            try:
                winreg.CloseKey(uninstall_key)
            except Exception:
                pass
        if registry is not None:
            try:
                winreg.CloseKey(registry)
            except Exception:
                pass

    return software_list


def getIISSoftware():
    registry = None
    iis_key = None
    try:
        registry = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
        access = winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)
        iis_key = winreg.OpenKey(
            registry,
            r"SOFTWARE\Microsoft\InetStp",
            0,
            access,
        )
        version = _registry_value(iis_key, "VersionString")
        if not version:
            major = _registry_value(iis_key, "MajorVersion")
            minor = _registry_value(iis_key, "MinorVersion")
            version = ".".join(value for value in (major, minor) if value)
        return [
            {
                "name": "Microsoft Internet Information Services",
                "version": version,
                "publisher": "Microsoft",
                "description": "",
            }
        ]
    except Exception:
        return []
    finally:
        if iis_key is not None:
            try:
                winreg.CloseKey(iis_key)
            except Exception:
                pass
        if registry is not None:
            try:
                winreg.CloseKey(registry)
            except Exception:
                pass

def getName():
    try:
        return platform.node()
    except Exception as err:
        classes.Err("Exception:"+str(err)+" at getName()")
        return None

def getArchitecture():
    try:
        return platform.architecture(sys.executable, '', '')[0]
    except Exception as err:
        classes.Err("Exception:"+str(err)+" at getArchitecture()")
        return None

def getCPUName():
    try:
        return platform.processor()
    except Exception as err:
        classes.Err("Exception:"+str(err)+" at getCPUName()")
        return None

def getCPUCoreCount():
    try:
        return psutil.cpu_count()
    except Exception as err:
        classes.Err("Exception:"+str(err)+" at getCPUCoreCount()")
        return 0

def getMachineType():
    try:
        return platform.machine()
    except Exception as err:
        classes.Err("Exception:"+str(err)+" at getCPUCoreCount()")
        return None

def getOS():
    try:
        return platform.system()+ " " +platform.release()+" " +platform.version()
    except Exception as err:
        classes.Err("Exception:"+str(err)+" at getOS()")
        return {}

def getMemory():
    try:
        memory = {}
        for field in psutil.virtual_memory()._fields:
            memory[field] = getattr(psutil.virtual_memory(), field)
        return memory
    except Exception as err:
        classes.Err("Exception:"+str(err)+" at getMemory()")
        return {}

def getDiskPartitions():
    try:
        partitions = []
        for disk in psutil.disk_partitions():
            partition = {}
            for field in disk._fields:
                partition[field] = getattr(disk, field)
            disk_usage = {}
            for field in psutil.disk_usage(disk.device)._fields:
                disk_usage[field] = getattr(psutil.disk_usage(disk.device), field)
            partition['disk_usage'] = disk_usage
            partitions.append(partition)
        return partitions
    except Exception as err:
        classes.Err("Exception:"+str(err)+" at getDiskPartitions()")
        return []

def getLBTS():
    try:
        return datetime.datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
    except Exception as err:
        classes.Err("Exception:"+str(err)+" at getLBTS()")
        return 0

def getIP():
    try:
        hostname = socket.gethostname()
        return socket.gethostbyname(hostname)
    except Exception as err:
        classes.Err("Exception:"+str(err)+" at getIP()")
        return 0

def getConnections():
    try:
        connections = []
        for conn in psutil.net_connections():
            if conn.status != 'None':
                connection = {}
                for field in conn._fields:
                    if field == 'laddr':
                        address = {}
                        addr = getattr(conn, field)
                        if len(addr) == 0:
                            address = {}
                        else:
                            for addr_field in addr._fields:
                                address[addr_field] = getattr(addr, addr_field)
                        connection[field] = address
                    elif field == 'raddr':
                        address = {}
                        addr = getattr(conn, field)
                        if len(addr) == 0:
                            address = {}
                        else:
                            for addr_field in addr._fields:
                                address[addr_field] = getattr(addr, addr_field)
                        connection[field] = address
                    else:
                        connection[field] = getattr(conn, field)
                connections.append(connection)
        return connections
    except Exception as err:
        classes.Err("Exception:"+str(err)+" at getConnections()")
        return []

def getIFAddresses():
    try:
        interfaces = []
        for net, addr in zip(psutil.net_if_addrs().keys(), psutil.net_if_addrs().values()):
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
                if x.family == -1:
                    interface['MAC']['addr'] = x.address
                    interface['MAC']['netmask'] = x.netmask
                elif x.family == 2:
                    interface['IPv4']['addr'] = x.address
                    interface['IPv4']['netmask'] = x.netmask
                elif x.family == 23:
                    interface['IPv6']['addr'] = x.address
                    interface['IPv6']['netmask'] = x.netmask
            interfaces.append(interface)
        return interfaces
    except Exception as err:
        classes.Err("Exception:"+str(err)+" at getIFAddresses()")
        return []

def getApplicationServerEvidence():
    view_32 = getInstalledSW(winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY)
    view_64 = getInstalledSW(winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY)
    if view_32 is None and view_64 is None:
        return None
    observations = (view_32 or []) + (view_64 or []) + (getIISSoftware() or [])
    software_list = []
    seen = set()
    for item in observations:
        key = (
            str(item.get("name") or "").strip().lower(),
            str(item.get("version") or "").strip(),
            str(item.get("publisher") or "").strip().lower(),
            str(item.get("install_location") or "").strip().lower(),
        )
        if not key[0] or key in seen:
            continue
        seen.add(key)
        software_list.append(item)
    return software_list
