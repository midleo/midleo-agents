import platform, sys, subprocess, datetime, re, multiprocessing, socket
try:
    __import__('imp').find_module('psutil')
except ImportError:
    pass
from modules import classes

def getName():
    try:
        return socket.getfqdn()
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
        command = "lscpu"
        all_info = subprocess.check_output(command, shell=True).strip()
        for line in all_info.split("\n".encode()):
            if b"Model name" in line:
                return re.sub( b".*Model name.*:", "".encode(), line,1).decode("utf-8").replace('  ','')
    except Exception as err:
        classes.Err("Exception:"+str(err)+" at getCPUName()")
        return None

def getCPUCoreCount():
    try:
        return multiprocessing.cpu_count()
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
        return platform.system()+ " " +platform.release()
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
            for field in psutil.disk_usage(disk.mountpoint)._fields:
                disk_usage[field] = getattr(psutil.disk_usage(disk.mountpoint), field)
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
