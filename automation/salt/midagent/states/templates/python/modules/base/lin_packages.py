import os
import shutil
import subprocess as sp

DEFAULT_TIMEOUT_SECONDS = int(os.environ.get("MIDLEO_PACKAGE_SCAN_TIMEOUT_SECONDS", "30"))
MAX_SOFTWARE_ITEMS = int(os.environ.get("MIDLEO_MAX_SOFTWARE_ITEMS", "20000"))


def _which(*names):
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return ""


def run(cmd, timeout=DEFAULT_TIMEOUT_SECONDS):
    try:
        return sp.check_output(
            cmd,
            stderr=sp.DEVNULL,
            timeout=timeout,
        ).decode("utf-8", errors="ignore").splitlines()
    except Exception:
        return []


def _append(software_list, name, version="", publisher="", description=""):
    if not name or len(software_list) >= MAX_SOFTWARE_ITEMS:
        return
    software_list.append(
        {
            "name": str(name).strip(),
            "version": str(version or "").strip(),
            "publisher": str(publisher or "").strip(),
            "description": str(description or "").strip(),
        }
    )


def get_flatpak():
    flatpak = _which("flatpak")
    if not flatpak:
        return []
    return run([flatpak, "list", "--app", "--columns=application,version"])


def get_apt():
    dpkg_query = _which("dpkg-query")
    if dpkg_query:
        return run([dpkg_query, "-W", "-f=${Package}\t${Version}\t${binary:Summary}\n"])
    dpkg = _which("dpkg")
    if dpkg:
        return run([dpkg, "-l"])
    return []


def get_rpm():
    rpm = _which("rpm")
    if not rpm:
        return []
    return run([rpm, "-qa", "--qf", "%{NAME}\t%{VERSION}-%{RELEASE}\t%{VENDOR}\n"])


def get_pkginfo():
    pkginfo = _which("pkginfo")
    if not pkginfo:
        return []
    return run([pkginfo, "-l"])


def get_pkgs11():
    pkg = _which("pkg")
    if not pkg:
        return []
    return run([pkg, "list", "-H"])


def _collect_flatpak(software_list):
    for line in get_flatpak():
        parts = line.split("\t")
        if len(parts) >= 2:
            _append(software_list, parts[0], parts[1], "flatpak")
        elif line.strip():
            _append(software_list, line.split()[0], "", "flatpak")


def _collect_debian(software_list):
    for line in get_apt():
        if "\t" in line:
            parts = line.split("\t", 2)
            if len(parts) >= 2:
                _append(
                    software_list,
                    parts[0],
                    parts[1],
                    "debian",
                    parts[2] if len(parts) > 2 else "",
                )
            continue

        if line.startswith("ii"):
            parts = line.split(None, 4)
            if len(parts) >= 5:
                _append(software_list, parts[1], parts[2], "debian", parts[4])


def _collect_rpm(software_list):
    for line in get_rpm():
        parts = line.split("\t", 2)
        if len(parts) >= 2:
            _append(
                software_list,
                parts[0],
                parts[1],
                parts[2] if len(parts) > 2 else "rpm",
            )


def _collect_pkginfo(software_list):
    name = version = None
    for raw_line in get_pkginfo():
        line = raw_line.strip()
        if line.startswith("PKGINST:"):
            name = line.split(":", 1)[1].strip()
        elif line.startswith("VERSION:"):
            version = line.split(":", 1)[1].strip()
        if name and version:
            _append(software_list, name, version, "solaris")
            name = version = None


def _collect_pkgs11(software_list):
    for line in get_pkgs11():
        parts = line.split()
        if len(parts) >= 2:
            _append(software_list, parts[0], parts[1], "solaris")


def getSoftware():
    software_list = []

    _collect_flatpak(software_list)

    if _which("dpkg-query", "dpkg"):
        _collect_debian(software_list)
    elif _which("rpm"):
        _collect_rpm(software_list)
    elif _which("pkginfo"):
        _collect_pkginfo(software_list)
    elif _which("pkg"):
        _collect_pkgs11(software_list)

    return software_list
