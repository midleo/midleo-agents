import platform, sys, os, psutil, socket, datetime, winreg, classes

def getInstalledSW(hive, flag):
    aReg = winreg.ConnectRegistry(None, hive)
    aKey = winreg.OpenKey(aReg, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                          0, winreg.KEY_READ | flag)

    count_subkey = winreg.QueryInfoKey(aKey)[0]

    software_list = []

    for i in range(count_subkey):
        software = {}
        try:
            asubkey_name = winreg.EnumKey(aKey, i)
            asubkey = winreg.OpenKey(aKey, asubkey_name)
            software['name'] = winreg.QueryValueEx(asubkey, "DisplayName")[0]

            try:
                software['version'] = winreg.QueryValueEx(asubkey, "DisplayVersion")[0]
            except EnvironmentError:
                software['version'] = 'undefined'
            try:
                software['publisher'] = winreg.QueryValueEx(asubkey, "Publisher")[0]
            except EnvironmentError:
                software['publisher'] = 'undefined'
            software_list.append(software)
        except EnvironmentError:
            continue

    return software_list

# config functions
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

# net functions
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
            for x in addr: # family: -1 -> MAC | 2 -> IPv4 | 23 -> IPv6
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

# installed software
def getSoftware():
    #software_list = getInstalledSW(winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY) + getInstalledSW(winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY) + getInstalledSW(winreg.HKEY_CURRENT_USER, 0)
    software_list = getInstalledSW(winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY) + getInstalledSW(winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY)
    return software_list
