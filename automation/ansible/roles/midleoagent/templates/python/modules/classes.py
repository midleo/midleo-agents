import platform, os
from datetime import datetime

def Err(logdata):
    now = datetime.now()
    current_time = now.strftime("%Y-%m-%d %H:%M:%S")
    logfile = open(os.getcwd()+"/logs/midleoagent.log", 'a')
    logfile.write(current_time+":"+logdata+ "\n")
    logfile.close()

class CPU:
    def __init__(self, name, num_cores):
        self.name = name
        self.num_cores = num_cores

class HWConfig:
    def __init__(self, name, os, architecture, machine_type, cpu, memory, disk_partitions, last_boot_time):
        self.name = name
        self.servtype = os
        self.servos = str(platform.system()).lower()
        self.architecture = architecture
        self.machineType = machine_type
        self.cpu = cpu
        self.memory = memory
        self.disk_partitions = disk_partitions
        self.last_boot_time = last_boot_time

class NetConfig:
    def __init__(self, dns, if_addresses):
        self.dns = dns
        self.if_addresses = if_addresses

class Config:
    def __init__(self, uid, groupid, agtver, updint, hw, net, geo, certs):
        self.uid = uid
        self.groupid = groupid
        self.agtver = agtver
        self.updint = updint
        self.hw_info = hw
        self.net_info = net
        self.installed_software = geo
        self.certs = certs
