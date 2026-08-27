import os
import shutil
import subprocess as sp
import threading

from modules.base import appsrv_catalog

DEFAULT_TIMEOUT_SECONDS = int(os.environ.get("MIDLEO_PACKAGE_SCAN_TIMEOUT_SECONDS", "30"))
MAX_SOFTWARE_ITEMS = int(os.environ.get("MIDLEO_MAX_SOFTWARE_ITEMS", "20000"))
MAX_PACKAGE_OUTPUT_BYTES = max(
    1024 * 1024,
    min(
        int(
            os.environ.get(
                "MIDLEO_MAX_PACKAGE_OUTPUT_BYTES", str(16 * 1024 * 1024)
            )
        ),
        64 * 1024 * 1024,
    ),
)


def _which(*names):
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return ""


def run(cmd, timeout=DEFAULT_TIMEOUT_SECONDS):
    if not isinstance(cmd, (list, tuple)) or not cmd:
        return None
    command = [str(value) for value in cmd]
    if not command[0] or not os.path.isfile(command[0]):
        return None

    process = None
    chunks = []
    output_size = [0]
    overflow = threading.Event()
    try:
        process = sp.Popen(
            command,
            stdin=sp.DEVNULL,
            stdout=sp.PIPE,
            stderr=sp.DEVNULL,
            shell=False,
        )

        def read_stdout():
            try:
                while True:
                    chunk = process.stdout.read(8192)
                    if not chunk:
                        break
                    remaining = MAX_PACKAGE_OUTPUT_BYTES - output_size[0]
                    if remaining > 0:
                        chunks.append(chunk[:remaining])
                        output_size[0] += min(len(chunk), remaining)
                    if len(chunk) > remaining:
                        overflow.set()
                        try:
                            process.kill()
                        except Exception:
                            pass
                        break
            except Exception:
                pass

        reader = threading.Thread(target=read_stdout, daemon=True)
        reader.start()
        try:
            return_code = process.wait(timeout=max(1, int(timeout)))
        except sp.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)
            return None
        finally:
            reader.join(timeout=1)

        if return_code != 0 or overflow.is_set():
            return None
        return b"".join(chunks).decode("utf-8", errors="ignore").splitlines()
    except Exception:
        return None
    finally:
        if process is not None and process.stdout is not None:
            try:
                process.stdout.close()
            except Exception:
                pass


def _append(software_list, name, version="", publisher="", description=""):
    if (
        not name
        or not appsrv_catalog.match_package_name(name)
        or len(software_list) >= MAX_SOFTWARE_ITEMS
    ):
        return
    software_list.append(
        {
            "name": str(name).strip(),
            "version": str(version or "").strip(),
            "publisher": str(publisher or "").strip(),
            "description": str(description or "").strip(),
        }
    )


def get_apt(package_tool=None):
    dpkg_query = (
        package_tool
        if package_tool and os.path.basename(package_tool).startswith("dpkg-query")
        else _which("dpkg-query")
    )
    if dpkg_query:
        return run([dpkg_query, "-W", "-f=${Package}\t${Version}\n"])
    dpkg = (
        package_tool
        if package_tool and os.path.basename(package_tool).startswith("dpkg")
        else _which("dpkg")
    )
    if dpkg:
        return run([dpkg, "-l"])
    return []


def get_rpm(rpm=None):
    rpm = rpm or _which("rpm")
    if not rpm:
        return []
    return run([rpm, "-qa", "--qf", "%{NAME}\t%{VERSION}-%{RELEASE}\n"])


def get_pkginfo(pkginfo=None):
    pkginfo = pkginfo or _which("pkginfo")
    if not pkginfo:
        return []
    return run([pkginfo, "-l"])


def get_pkgs11(pkg=None):
    pkg = pkg or _which("pkg")
    if not pkg:
        return []
    return run([pkg, "list", "-H"])


def _collect_debian(software_list, package_tool=None):
    for line in get_apt(package_tool):
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


def _collect_rpm(software_list, rpm=None):
    for line in get_rpm(rpm):
        parts = line.split("\t", 2)
        if len(parts) >= 2:
            _append(
                software_list,
                parts[0],
                parts[1],
                parts[2] if len(parts) > 2 else "rpm",
            )


def _collect_pkginfo(software_list, pkginfo=None):
    name = version = None
    for raw_line in get_pkginfo(pkginfo):
        line = raw_line.strip()
        if line.startswith("PKGINST:"):
            name = line.split(":", 1)[1].strip()
        elif line.startswith("VERSION:"):
            version = line.split(":", 1)[1].strip()
        if name and version:
            _append(software_list, name, version, "solaris")
            name = version = None


def _collect_pkgs11(software_list, pkg=None):
    for line in get_pkgs11(pkg):
        parts = line.split()
        if len(parts) >= 2:
            _append(software_list, parts[0], parts[1], "solaris")


def getApplicationServerEvidence():
    software_list = []

    package_tool = _which("dpkg-query", "dpkg", "rpm", "pkginfo", "pkg")
    if not package_tool:
        return None
    tool_name = os.path.basename(package_tool)
    try:
        if tool_name.startswith("dpkg"):
            _collect_debian(software_list, package_tool)
        elif tool_name == "rpm":
            _collect_rpm(software_list, package_tool)
        elif tool_name == "pkginfo":
            _collect_pkginfo(software_list, package_tool)
        elif tool_name == "pkg":
            _collect_pkgs11(software_list, package_tool)
    except Exception:
        return None

    return software_list
