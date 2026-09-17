
import os
import platform
import re
import signal
import shutil
import subprocess
import threading

from modules.base import appsrv_catalog, classes, configs


try:
    DEFAULT_CMD_TIMEOUT = max(1, min(30, int(
        configs.getcfgData().get("APPSRV_CMD_TIMEOUT_SECONDS", "3")
    )))
except (TypeError, ValueError):
    DEFAULT_CMD_TIMEOUT = 3
MAX_COMMAND_OUTPUT_BYTES = 64 * 1024
ZOS_OS_TYPES = frozenset(("os/390", "z/os"))

_INVALID_VERSIONS = frozenset(("", "undefined", "none", "null", "n/a", "unknown"))
_EPOCH_RE = re.compile(r"^\d+:")
_VERSION_PATTERN = (
    r"\d+(?:\.\d+){1,7}"
    r"(?:[._-](?:final|ga|cr|sp|alpha|beta|rc)(?:\.?\d+)*)?"
    r"(?:\+[0-9a-z-]+(?:\.[0-9a-z-]+)*)?"
)
_VERSION_RE = re.compile(r"(?<![a-z0-9])v?(" + _VERSION_PATTERN + r")", re.IGNORECASE)
_PURE_VERSION_RE = re.compile(r"^\s*v?" + _VERSION_PATTERN + r"\s*$", re.IGNORECASE)
_VERSION_LABEL_RE = re.compile(r"\b(?:product\s+)?version\b", re.IGNORECASE)
_IBM_MQ_RPM_VERSION_RE = re.compile(
    r"^(\d+\.\d+\.\d+)-(\d+)(?:\.[a-z0-9_.-]+)?$", re.IGNORECASE
)


def _safe_lower(value):
    try:
        return str(value or "").strip().lower()
    except Exception:
        return ""


def normalize_version(raw, product_type=""):
    """Extract a product version without retaining package-manager releases."""
    try:
        text = str(raw or "").strip()
    except Exception:
        return ""
    if text.lower() in _INVALID_VERSIONS:
        return ""

    text = _EPOCH_RE.sub("", text, count=1)
    if product_type in ("ibmmq", "fte"):
        mq_match = _IBM_MQ_RPM_VERSION_RE.fullmatch(text)
        if mq_match:
            return mq_match.group(1) + "." + mq_match.group(2)

    match = _VERSION_RE.search(text)
    return match.group(1) if match else ""


def match_software_item(item, os_type=""):
    """Return at most one canonical product key for an inventory row."""
    if not isinstance(item, dict):
        return []
    name = item.get("name")
    if not _safe_lower(name):
        return []

    key = appsrv_catalog.match_package_name(name)
    if not key and _safe_lower(os_type) == "windows":
        key = appsrv_catalog.match_windows_display_name(
            name, item.get("publisher")
        )
    return [key] if key else []


def _normalize_records(records):
    cleaned = []
    seen = set()
    for item in records or ():
        if not isinstance(item, dict):
            continue
        product_type = str(item.get("type") or "").strip()
        if product_type not in appsrv_catalog.SUPPORTED_KEYS:
            continue
        version = normalize_version(item.get("version"), product_type)
        record_key = (product_type, version)
        if record_key in seen:
            continue
        seen.add(record_key)
        cleaned.append({"type": product_type, "version": version})
    cleaned.sort(key=lambda row: (row["type"], row["version"]))
    return cleaned


def _parse_version_output(text):
    if not text:
        return ""
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]

    # Prefer explicitly labelled product-version lines. This avoids returning a
    # copyright year, Java level, installer level, or an error-code number.
    for line in lines:
        if _VERSION_LABEL_RE.search(line):
            version = normalize_version(line)
            if version:
                return version

    for line in lines:
        if _PURE_VERSION_RE.fullmatch(line):
            return normalize_version(line)
    return ""


def _default_which(name):
    try:
        return shutil.which(name) or ""
    except Exception:
        return ""


def _default_run_command(argv, timeout=DEFAULT_CMD_TIMEOUT):
    """Run a fixed detector command with timeout and bounded captured output."""
    if not isinstance(argv, (list, tuple)) or not argv:
        return ""
    command = [str(value) for value in argv]
    if not command[0] or not os.path.isfile(command[0]):
        return ""

    process = None
    reader = None
    chunks = []
    output_size = [0]
    overflow = threading.Event()

    def stop_detector():
        if process is None:
            return
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            elif process.poll() is None:
                # Version scripts can launch Java children which inherit stdout.
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=2, creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception:
            pass
        if process.poll() is None:
            try:
                process.kill()
            except Exception:
                pass

    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            shell=False,
            start_new_session=os.name == "posix",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        def read_stdout():
            try:
                while True:
                    chunk = process.stdout.read(4096)
                    if not chunk:
                        break
                    remaining = MAX_COMMAND_OUTPUT_BYTES - output_size[0]
                    if remaining > 0:
                        chunks.append(chunk[:remaining])
                        output_size[0] += min(len(chunk), remaining)
                    if len(chunk) > remaining:
                        overflow.set()
                        try:
                            stop_detector()
                        except Exception:
                            pass
                        break
            except Exception:
                pass

        reader = threading.Thread(target=read_stdout, daemon=True)
        reader.start()
        try:
            return_code = process.wait(
                timeout=max(1, int(timeout or DEFAULT_CMD_TIMEOUT))
            )
        except subprocess.TimeoutExpired:
            stop_detector()
            process.wait(timeout=1)
            return ""
        finally:
            reader.join(timeout=1)

        if reader.is_alive():
            stop_detector()
            reader.join(timeout=1)
            return ""
        if return_code != 0 or overflow.is_set():
            return ""
        return b"".join(chunks).decode("utf-8", errors="ignore")
    except Exception:
        if process is not None:
            try:
                stop_detector()
            except Exception:
                pass
        return ""
    finally:
        if process is not None and process.stdout is not None and (reader is None or not reader.is_alive()):
            try:
                process.stdout.close()
            except Exception:
                pass


def _default_path_exists(path):
    try:
        return os.path.isfile(os.path.expandvars(path))
    except Exception:
        return False


def _collect_package_hits(software_list, os_type):
    hits = {}
    for item in software_list or ():
        if not isinstance(item, dict):
            continue
        try:
            keys = match_software_item(item, os_type=os_type)
            for key in keys:
                version = normalize_version(item.get("version"), key)
                if key == "aap":
                    name = _safe_lower(item.get("name")).split(":", 1)[0]
                    if name != "ansible-automation-platform" and "ansible automation platform" not in name:
                        # Controller/hub/Tower versions are not AAP platform versions.
                        version = ""
                bucket = hits.setdefault(
                    key, {"versions": set(), "preferred_versions": set()}
                )
                bucket["versions"].add(version)
                if appsrv_catalog.is_preferred_package(key, item.get("name")):
                    bucket["preferred_versions"].add(version)
        except Exception:
            continue
    return hits


def _run_version_detector(spec, which_fn, run_command_fn):
    for detector in spec.get("version_binaries") or ():
        binary = detector.get("binary")
        if not binary:
            continue
        try:
            resolved = which_fn(binary)
            if not resolved:
                continue
            output = run_command_fn(
                [resolved] + list(detector.get("args") or ()),
                detector.get("timeout", DEFAULT_CMD_TIMEOUT),
            )
            version = _parse_version_output(output)
            if version:
                return version, bool(detector.get("prefer"))
        except Exception:
            continue
    return "", False


def _path_hint_evidence(spec, os_type, path_exists_fn):
    allowed = tuple(_safe_lower(value) for value in (spec.get("os") or ()))
    if allowed and _safe_lower(os_type) not in allowed:
        return False
    for path in spec.get("path_hints") or ():
        try:
            if path_exists_fn(path):
                return True
        except Exception:
            continue
    return False


def discover_application_servers(
    software_list,
    os_type="",
    os_release="",
    which_fn=None,
    run_command_fn=None,
    path_exists_fn=None,
    **_ignored,
):
    """Return deterministic ``[{type, version}, ...]`` product facts."""
    os_type = os_type or platform.system()
    os_release = os_release or platform.release()
    which_fn = which_fn or _default_which
    run_command_fn = run_command_fn or _default_run_command
    path_exists_fn = path_exists_fn or _default_path_exists

    try:
        hits = _collect_package_hits(software_list, os_type)
    except Exception as ex:
        classes.Err("Exception in application server package match: " + str(ex))
        hits = {}

    records = []
    for key, spec in appsrv_catalog.iter_products():
        try:
            if spec.get("detect_from_os"):
                if _safe_lower(os_type) in ZOS_OS_TYPES:
                    records.append(
                        {"type": key, "version": normalize_version(os_release, key)}
                    )
                continue

            allowed = tuple(_safe_lower(value) for value in (spec.get("os") or ()))
            if allowed and _safe_lower(os_type) not in allowed:
                continue

            hit = hits.get(key)
            if hit is None:
                if _path_hint_evidence(spec, os_type, path_exists_fn):
                    records.append({"type": key, "version": ""})
                continue

            preferred = hit.get("preferred_versions") or set()
            versions = preferred or hit.get("versions") or set()
            usable = sorted(version for version in versions if version)

            should_run_version = not usable or any(
                detector.get("prefer")
                for detector in (spec.get("version_binaries") or ())
            )
            if should_run_version:
                detected, prefer_detected = _run_version_detector(
                    spec, which_fn, run_command_fn
                )
                if detected:
                    # One default-path executable cannot invalidate evidence of
                    # several installed product versions.
                    usable = [detected] if prefer_detected and len(usable) <= 1 else sorted(
                        set(usable + [detected])
                    )

            if not usable:
                usable = [""]
            for version in usable:
                records.append({"type": key, "version": version})
        except Exception as ex:
            classes.Err("Exception discovering " + str(key) + ": " + str(ex))

    return _normalize_records(records)
