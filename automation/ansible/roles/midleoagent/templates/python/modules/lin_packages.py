import subprocess as sp
from os import path
import re

def get_flatpak():
    cmd=['/usr/bin/flatpak','list','--app','--show-details']
    process=sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE)
    stdout, stderr = process.communicate()
    return stdout.decode().replace('\t',' ').split('\n')

def get_apt():
    cmd=['/usr/bin/dpkg','-l']
    process=sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE)
    stdout, stderr = process.communicate()
    return re.sub(' {2,}', '#',stdout.decode().replace('\t',' ')).split('\n')

def get_yum():
    cmd=['/usr/bin/yum','list','installed']
    process=sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE)
    stdout, stderr = process.communicate()
    return stdout.decode().replace('\t',' ').split('\n')

def get_rpm():
    cmd=['/usr/bin/rpm','-qa']
    process=sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE)
    stdout, stderr = process.communicate()
    return stdout.decode().replace('\t',' ').split('\n')

def get_pkginfo():
    cmd=['/usr/bin/pkginfo -l | egrep "(PKGINST|VERSION)" | sed "s/  *//g" | awk "{print}" ORS=" "']
    process=sp.Popen(cmd, shell=True, stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.PIPE)
    stdout, stderr = process.communicate()
    return stdout.decode().replace('\t',' ').replace('PKGINST:','\n').replace('VERSION:','').split('\n')

def get_pkgs11():
    cmd=['/usr/bin/pkg','list']
    process=sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE)
    stdout, stderr = process.communicate()
    return stdout.decode().replace('\t',' ').split('\n')

def getSoftware():

    software_list = []
    flatpak = False
    apt = False      #for ubuntu
    yum = False      #for fedora
    rpm = False
    pkginfo = False  #for solaris 10
    pkgs11 = False  #for solars 11

    if path.exists("/usr/bin/flatpak"):
       flatpak = True

    if path.exists("/usr/bin/dpkg"):
       apt = True

    if path.exists("/usr/bin/rpm"):
       rpm = True
    
    if path.exists("/usr/bin/pkginfo"):
       pkginfo = True

    if path.exists("/usr/bin/pkg"):
       pkgs11 = True

    if path.exists("/usr/bin/yum"):
       yum = True
       rpm = False

    if flatpak:
        pkgs = get_flatpak()
        for pkg in pkgs:
            if ' ' in pkg:
                software_list.append(pkg.split()[0])

    if apt:
        pkgs = get_apt()
        for pkg in pkgs:
            if ' ' in pkg and len(pkg.split('#'))>4:
                software = {}
                software['name']=pkg.split('#')[1]
                software['version']=pkg.split('#')[2]
                software['publisher']=pkg.split('#')[-1]
                software_list.append(software)

    if pkginfo:
        pkgs = get_pkginfo()
        for pkg in pkgs:
            if ' ' in pkg:
                software = {}
                software['name']=pkg.split()[0]
                software['version']=pkg.split()[1]
                software['publisher'] = 'undefined'
                software_list.append(software)

    if pkgs11:
        pkgs = get_pkgs11()
        for pkg in pkgs:
            if ' ' in pkg:
                software_list.append(pkg.split()[0])

    if rpm:
        pkgs = get_rpm()
        for pkg in pkgs:
            if ' ' in pkg:
                software_list.append(pkg.split()[0])

    if yum:
        pkgs = get_yum()
        for pkg in pkgs:
            if ' ' in pkg and len(pkg.split())>2:
                software = {}
                software['name']=pkg.split()[0]
                software['version']=pkg.split()[1]
                software['publisher'] = pkg.split()[2]
                software_list.append(software)

    return software_list

