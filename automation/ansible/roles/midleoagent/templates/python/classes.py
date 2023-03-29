class Err:
    def __init__(self, error):
        self.error = error

class CPU:
    def __init__(self, name, num_cores):
        self.name = name
        self.num_cores = num_cores

class HWConfig:
    def __init__(self, name, os, architecture, machine_type, cpu, memory, disk_partitions, last_boot_time):
        self.name = name
        self.servtype = os
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
    def __init__(self, uid, groupid, updint, hw, net, geo):
        self.uid = uid
        self.groupid = groupid
        self.updint = updint
        self.hw_info = hw
        self.net_info = net
        self.installed_software = geo