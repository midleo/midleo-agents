import subprocess as sp
from os import path
import re

def run(cmd, shell=False):
    return sp.check_output(cmd, shell=shell, stderr=sp.DEVNULL).decode("utf-8", errors="ignore").splitlines()

def get_flatpak():
    return run(["flatpak", "list", "--app"])

def get_apt():
    return run(["dpkg", "-l"])

def get_yum():
    return run(["yum", "list", "installed"])

def get_rpm():
    return run('rpm -qa --qf "%{NAME} %{VERSION} %{VENDOR}\n"', shell=True)

def get_pkginfo():
    return run('pkginfo -l | egrep "(PKGINST|VERSION)" | sed "s/  *//g" | awk "{print}" ORS=" "', shell=True)

def get_pkgs11():
    return run(["pkg", "list", "-H"])

def getSoftware():
    software_list = []

    if path.exists("/usr/bin/flatpak"):
        for pkg in get_flatpak():
            if pkg:
                software_list.append({"name": pkg.split()[0], "version": "", "publisher": "flatpak", "description": ""})
        return software_list

    if path.exists("/usr/bin/dpkg"):
        for line in get_apt():
            if line.startswith("ii"):
                parts = line.split(None, 4)
                if len(parts) >= 5:
                    software_list.append({
                        "name": parts[1],
                        "version": parts[2],
                        "publisher": "debian",
                        "description": parts[4]
                    })
        return software_list

    if path.exists("/usr/bin/yum"):
        for pkg in get_yum():
            parts = pkg.split()
            if len(parts) >= 3 and "." in parts[0]:
                software_list.append({
                    "name": parts[0],
                    "version": parts[1],
                    "publisher": parts[2],
                    "description": ""
                })
        return software_list

    if path.exists("/usr/bin/rpm"):
        for pkg in get_rpm():
            parts = pkg.split(None, 2)
            if len(parts) == 3:
                software_list.append({
                    "name": parts[0],
                    "version": parts[1],
                    "publisher": parts[2],
                    "description": ""
                })
        return software_list

    if path.exists("/usr/bin/pkginfo"):
        name = version = None
        for line in get_pkginfo():
            if line.startswith("PKGINST:"):
                name = line.split(":", 1)[1]
            elif line.startswith("VERSION:"):
                version = line.split(":", 1)[1]
            if name and version:
                software_list.append({
                    "name": name,
                    "version": version,
                    "publisher": "solaris",
                    "description": ""
                })
                name = version = None
        return software_list

    if path.exists("/usr/bin/pkg"):
        for pkg in get_pkgs11():
            parts = pkg.split()
            if len(parts) >= 2:
                software_list.append({
                    "name": parts[0],
                    "version": parts[1],
                    "publisher": "solaris",
                    "description": ""
                })
        return software_list

    return software_list
