import asyncio
import base64
import json
import os
import re
import shlex
import subprocess
import tempfile
import zlib
from datetime import datetime

from modules.base import classes, configs, decrypt, secrets

PORT_NUMBER = 5550
AGENT_VER = "1.26.05"

MAX_FRAME_BYTES = 2 * 1024 * 1024
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_COMMAND_OUTPUT_BYTES = 512 * 1024
MAX_CONCURRENT_CLIENTS = 25
READ_TIMEOUT = 30
CMD_TIMEOUT = 300

CLIENT_SEMAPHORE = None

FORBIDDEN_PATTERNS = [
    r"\brm\s+-[rRfF]+\s+/",
    r"\bchown\s+-[rRfF]+\s+/",
    r"\bchmod\s+-[rRfF]+\s+/",
    r"\bdd\s+if=",
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\};:",
    r">\s*/dev/sd[a-z]",
    r">\s*/dev/nvme",
    r"\bmkfs\b",
    r"\bwipefs\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bpoweroff\b",
    r"\brm\s+(-[^\s]+\s+)?\*",
]

SHELL_META_CHARS = set("|&;<>\n`")
AGENT_SCRIPT_COMMANDS = {"magent.sh", "magent.bat", "cronjobs.sh", "cronjobs.bat"}

def _get_cfg():
    cfg = configs.getcfgData() or {}
    srvuid = str(cfg.get("SRVUID", ""))
    if not srvuid or not re.fullmatch(r"[0-9A-Fa-f]+", srvuid):
        raise RuntimeError("SRVUID is missing or invalid")
    uid_key = srvuid * 4

    allowed_cmds = cfg.get("ALLOWED_COMMANDS", [])
    if isinstance(allowed_cmds, str):
        allowed_cmds = [c.strip() for c in allowed_cmds.split(",") if c.strip()]
    allowed_cmds = [str(c) for c in allowed_cmds]

    roots_raw = str(cfg.get("REMOTE_FILE_ROOTS", "")).strip()
    remote_roots = [x.strip() for x in roots_raw.split(",") if x.strip()]
    if not remote_roots:
        remote_roots = [os.getcwd()]

    allow_shell = str(cfg.get("ALLOW_SHELL_COMMANDS", "n")).strip().lower() in (
        "y",
        "yes",
        "true",
        "1",
    )

    bind_host = str(cfg.get("AGENT_BIND_HOST", "0.0.0.0")).strip() or "0.0.0.0"

    return {
        "uid_key": uid_key,
        "allowed_cmds": allowed_cmds,
        "allow_shell": allow_shell,
        "remote_roots": remote_roots,
        "bind_host": bind_host,
    }


async def _read_framed_or_legacy(reader: asyncio.StreamReader) -> bytes:
    try:
        hdr = await asyncio.wait_for(reader.readexactly(4), timeout=READ_TIMEOUT)
    except Exception:
        return await asyncio.wait_for(
            reader.read(MAX_FRAME_BYTES), timeout=READ_TIMEOUT
        )

    frame_len = int.from_bytes(hdr, "big", signed=False)
    if frame_len <= 0 or frame_len > MAX_FRAME_BYTES:
        rest = await asyncio.wait_for(
            reader.read(MAX_FRAME_BYTES), timeout=READ_TIMEOUT
        )
        return hdr + rest

    return await asyncio.wait_for(reader.readexactly(frame_len), timeout=READ_TIMEOUT)


def _decode_json_bytes(b: bytes):
    s = b.strip()
    if not s:
        raise ValueError("empty")
    if isinstance(s, (bytes, bytearray)):
        s = s.decode("utf-8", errors="strict")
    return json.loads(s)


def _reply(now_str, parts, cfgkey):
    payload = {"time": now_str, "log": parts}
    encoded = json.dumps(payload, ensure_ascii=False)
    encrypted = decrypt.encrypt(encoded, cfgkey)
    return (
        encrypted
        if isinstance(encrypted, bytes)
        else encrypted.encode("utf-8", errors="replace")
    )


def _sanitize(text):
    return secrets.redact_text(text)


def _split_commands(raw):
    raw = raw.strip()
    if not raw:
        return []

    try:
        decoded = json.loads(raw)
        if isinstance(decoded, list):
            return [str(item).strip() for item in decoded if str(item).strip()]
    except Exception:
        pass

    commands = []
    current = []
    quote = None
    escaped = False

    for char in raw:
        if escaped:
            current.append(char)
            escaped = False
            continue

        if char == "\\" and quote != "'":
            current.append(char)
            escaped = True
            continue

        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue

        if char in ("'", '"'):
            quote = char
            current.append(char)
            continue

        if char == ";":
            command = "".join(current).strip()
            if command:
                commands.append(command)
            current = []
            continue

        current.append(char)

    command = "".join(current).strip()
    if command:
        commands.append(command)

    return commands


def _contains_unquoted_shell_syntax(value):
    quote = None
    escaped = False

    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue

        if char == "\\" and quote != "'":
            escaped = True
            continue

        if quote:
            if char == quote:
                quote = None
            continue

        if char in ("'", '"'):
            quote = char
            continue

        if char in SHELL_META_CHARS:
            return True

        if char == "$" and index + 1 < len(value) and value[index + 1] in ("(", "{"):
            return True

    return False


def _extract_json_object_arg(value):
    start = value.find("{")
    if start < 0:
        return None

    decoder = json.JSONDecoder()
    try:
        parsed, end = decoder.raw_decode(value[start:])
    except ValueError:
        return None

    if not isinstance(parsed, dict):
        return None

    prefix = value[:start].rstrip()
    if prefix.endswith("'") or prefix.endswith('"'):
        prefix = prefix[:-1].rstrip()

    tail = value[start + end:].strip()
    if tail and any(ch not in ("'", '"') for ch in tail):
        return None

    return prefix, value[start:start + end]


def _magent_json_args(cmd_str):
    extracted = _extract_json_object_arg(cmd_str)
    if extracted is None:
        return None

    prefix, json_text = extracted
    if _contains_unquoted_shell_syntax(prefix):
        raise ValueError("shell metacharacters are not allowed")

    try:
        args = shlex.split(prefix, posix=os.name != "nt")
    except ValueError as ex:
        raise ValueError("invalid command syntax: " + str(ex))

    if len(args) < 2:
        return None

    script = os.path.basename(args[0]).lower()
    if script not in ("magent.sh", "magent.bat"):
        return None

    if args[1] not in ("enableavl", "addcert", "addappstat", "addoptadvisor", "addaction"):
        return None

    return args + [json_text]


def _command_args(cmd_str):
    magent_args = _magent_json_args(cmd_str)
    if magent_args is not None:
        return magent_args

    if _contains_unquoted_shell_syntax(cmd_str):
        raise ValueError("shell metacharacters are not allowed")

    try:
        return shlex.split(cmd_str, posix=os.name != "nt")
    except ValueError as ex:
        raise ValueError("invalid command syntax: " + str(ex))


def _command_index(args):
    if not args:
        raise ValueError("empty command")

    index = 0
    exe = os.path.basename(args[index]).lower()
    if exe.endswith(".exe"):
        exe = exe[:-4]

    if exe == "env":
        for idx, item in enumerate(args[1:], start=1):
            if "=" not in item:
                index = idx
                break
        exe = os.path.basename(args[index]).lower()
        if exe.endswith(".exe"):
            exe = exe[:-4]

    if exe == "busybox" and len(args) > index + 1:
        index = index + 1

    return index


def _command_exe(args):
    index = _command_index(args)
    exe = os.path.basename(args[index]).lower()
    if exe.endswith(".exe"):
        exe = exe[:-4]
    return exe


def _normalize_exe(value):
    exe = os.path.basename(value).lower()
    return exe[:-4] if exe.endswith(".exe") else exe


def _validate_command(cmd_str, allowed):
    if not cmd_str or not cmd_str.strip():
        raise ValueError("empty command")

    cmd_l = cmd_str.lower()
    for pat in FORBIDDEN_PATTERNS:
        if re.search(pat, cmd_l):
            classes.Err(
                "Forbidden command blocked. Command: "
                + _sanitize(cmd_str)
                + " | Pattern: "
                + pat
            )
            raise ValueError("forbidden command pattern detected")

    args = _command_args(cmd_str)
    cmd_index = _command_index(args)
    exe = _command_exe(args)
    allowed_set = {_normalize_exe(a) for a in allowed if a}
    if not allowed_set:
        raise ValueError("command allowlist is empty")
    if exe not in allowed_set:
        raise ValueError("command not allowed")

    if exe in AGENT_SCRIPT_COMMANDS:
        expected = os.path.realpath(os.path.join(os.getcwd(), exe))
        candidate_raw = args[cmd_index]
        candidate = os.path.realpath(
            candidate_raw
            if os.path.isabs(candidate_raw)
            else os.path.join(os.getcwd(), candidate_raw)
        )
        if candidate != expected:
            raise ValueError("agent script path not allowed")
        args[cmd_index] = expected

    return args


async def _run_command(cmd_str, allowed, allow_shell):
    args = _validate_command(cmd_str, allowed)

    def _do():
        if allow_shell:
            run_target = cmd_str
            use_shell = True
        else:
            run_target = args
            use_shell = False

        r = subprocess.run(
            run_target,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=CMD_TIMEOUT,
            text=False,
            shell=use_shell,
        )
        out = (r.stdout or b"")[:MAX_COMMAND_OUTPUT_BYTES]
        return r.returncode, out.decode("utf-8", errors="replace").strip()

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do)


async def _close_writer(writer):
    writer.close()
    wait_closed = getattr(writer, "wait_closed", None)
    if wait_closed is not None:
        await wait_closed()


def _safe_path(filename, roots):
    if not filename or "\x00" in filename:
        raise ValueError("invalid filename")

    candidate = filename if os.path.isabs(filename) else os.path.join(os.getcwd(), filename)
    real_candidate = os.path.realpath(candidate)

    for root in roots:
        real_root = os.path.realpath(root)
        try:
            if os.path.commonpath([real_root, real_candidate]) == real_root:
                return real_candidate
        except ValueError:
            continue

    raise ValueError("file path outside allowed roots")


def _decompress_file(encoded_file):
    raw = base64.b64decode(encoded_file)
    decompressor = zlib.decompressobj()
    content = decompressor.decompress(raw, MAX_FILE_BYTES + 1)
    content += decompressor.flush()
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("file is too large")
    return content.decode("utf-8").replace("\r", "")


def _write_remote_file(filename, encoded_file, roots):
    safe_filename = _safe_path(filename, roots)
    content = _decompress_file(encoded_file)
    directory = os.path.dirname(safe_filename)
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".mwagent_", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.chmod(tmp_path, 0o640)
        os.replace(tmp_path, safe_filename)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _delete_remote_file(filename, roots):
    safe_filename = _safe_path(filename, roots)
    os.remove(safe_filename)


async def _handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    cfg = _get_cfg()
    addr = writer.get_extra_info("peername")
    classes.Err("Info:Connected by " + str(addr))
    now = datetime.now().strftime("%H:%M:%S")

    try:
        raw = await _read_framed_or_legacy(reader)
        datamess = _decode_json_bytes(raw)

        decrypted = decrypt.decryptit(datamess["data"], cfg["uid_key"])
        data = json.loads(decrypted) if isinstance(decrypted, str) else decrypted
        if not isinstance(data, dict):
            raise ValueError("invalid payload")

        if data.get("uid") != cfg["uid_key"]:
            raise ValueError("unauthorized")

        responses = []

        files = data.get("files", [])
        if not isinstance(files, list):
            raise ValueError("files must be a list")

        for f in files:
            if not isinstance(f, dict):
                continue

            ftype = f.get("ftype")
            filename = f.get("filename")

            if ftype == "create" and filename and f.get("file"):
                try:
                    _write_remote_file(filename, f["file"], cfg["remote_roots"])
                    responses.append("File created:" + filename)
                except Exception as ex:
                    responses.append("File write failed:" + str(filename) + " (" + str(ex) + ")")

            elif ftype == "delete" and filename:
                try:
                    _delete_remote_file(filename, cfg["remote_roots"])
                    responses.append("File deleted:" + filename)
                except Exception as ex:
                    responses.append("File delete failed:" + str(filename) + " (" + str(ex) + ")")

        if "command" in data:
            cmd_raw = base64.b64decode(data["command"]).decode("utf-8", errors="strict")
            commands = _split_commands(cmd_raw)

            for cmd in commands:
                rc, out = await _run_command(
                    cmd, cfg["allowed_cmds"], cfg["allow_shell"]
                )
                sanitized = _sanitize(cmd)
                classes.Err("Command:" + sanitized + " from " + str(addr))
                responses.extend(
                    ["Command:" + sanitized, "RC:" + str(rc), "Output:" + out]
                )

        if not responses:
            responses.append("Command:empty!")

        writer.write(_reply(now, responses, cfg["uid_key"]))
        await writer.drain()
        await _close_writer(writer)
        classes.Err("Info:Disconnected " + str(addr))

    except Exception as ex:
        classes.Err("Error:Disconnecting " + str(addr) + " reason=" + str(ex))
        try:
            writer.write(
                _reply(
                    datetime.now().strftime("%H:%M:%S"),
                    ["Error in receive:" + str(ex)],
                    cfg["uid_key"],
                )
            )
            await writer.drain()
        except Exception:
            pass
        try:
            await _close_writer(writer)
        except Exception:
            pass


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    async with CLIENT_SEMAPHORE:
        await _handle_client(reader, writer)


async def main():
    global CLIENT_SEMAPHORE
    classes.ClearLog()
    CLIENT_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_CLIENTS)
    cfg = _get_cfg()
    server = await asyncio.start_server(
        handle_client, host=cfg["bind_host"], port=PORT_NUMBER, backlog=100
    )
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        server.close()
        await server.wait_closed()


def _run_async_main(coro):
    run = getattr(asyncio, "run", None)
    if run is not None:
        run(coro)
        return

    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(coro)
    finally:
        loop.close()


if __name__ == "__main__":
    _run_async_main(main())
