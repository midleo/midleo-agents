import asyncio
import re
import base64
import json
import os
import zlib
import subprocess
from datetime import datetime

from modules.base import decrypt, classes, configs

PORT_NUMBER = 5550
AGENT_VER = "1.26.02"

MAX_FRAME_BYTES = 2 * 1024 * 1024
MAX_COMMAND_OUTPUT_BYTES = 512 * 1024
READ_TIMEOUT = 10
CMD_TIMEOUT = 20

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


def _get_cfg():
    cfg = configs.getcfgData() or {}
    srvuid = str(cfg.get("SRVUID", ""))
    uid_key = srvuid * 4

    allowed_cmds = cfg.get("ALLOWED_COMMANDS", [])
    if isinstance(allowed_cmds, str):
        allowed_cmds = [c.strip() for c in allowed_cmds.split(",") if c.strip()]
    allowed_cmds = [str(c) for c in allowed_cmds]

    return {"uid_key": uid_key, "allowed_cmds": allowed_cmds}


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


def _reply(now_str: str, parts: list[str], cfgkey: str) -> bytes:
    data_field = "Time:" + now_str + "\n" + "\n".join(parts)
    encrypted = decrypt.encrypt(data_field, cfgkey)
    return (
        encrypted
        if isinstance(encrypted, bytes)
        else encrypted.encode("utf-8", errors="replace")
    )


async def _run_command(cmd_str: str, allowed: list[str]) -> tuple[int, str]:
    if not cmd_str or not cmd_str.strip():
        raise ValueError("empty command")

    cmd_l = cmd_str.lower()
    for pat in FORBIDDEN_PATTERNS:
        if re.search(pat, cmd_l):
            classes.Err(
                "Forbidden command blocked. Command: " + cmd_str + " | Pattern: " + pat
            )
            raise ValueError("forbidden command pattern detected")

    first = cmd_str.strip().split()[0]
    exe = os.path.basename(first).lower()
    if exe.endswith(".exe"):
        exe = exe[:-4]

    if exe in ("env", "busybox"):
        parts = cmd_str.strip().split()
        if len(parts) > 1:
            exe = os.path.basename(parts[1]).lower()
            if exe.endswith(".exe"):
                exe = exe[:-4]

    allowed_set = {os.path.basename(a).lower() for a in allowed if a}
    if allowed_set and exe not in allowed_set:
        raise ValueError("command not allowed")

    def _do():
        r = subprocess.run(
            cmd_str,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=CMD_TIMEOUT,
            text=False,
            shell=True,
        )
        out = (r.stdout or b"")[:MAX_COMMAND_OUTPUT_BYTES]
        return r.returncode, out.decode("utf-8", errors="replace").strip()

    return await asyncio.to_thread(_do)


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    cfg = _get_cfg()
    addr = writer.get_extra_info("peername")
    classes.Err("Info:Connected by " + str(addr))
    now = datetime.now().strftime("%H:%M:%S")

    try:
        raw = await _read_framed_or_legacy(reader)
        datamess = _decode_json_bytes(raw)

        decrypted = decrypt.decryptit(datamess["data"], cfg["uid_key"])
        data = json.loads(decrypted)

        if data.get("uid") != cfg["uid_key"]:
            raise ValueError("unauthorized")

        ftype = data.get("ftype", "")
        filename = data.get("filename")

        if ftype == "create" and filename and "file" in datamess:
            try:
                rawf = base64.b64decode(datamess["file"])
                content = zlib.decompress(rawf).decode("utf-8").replace("\r", "")
                os.makedirs(os.path.dirname(filename), exist_ok=True)
                with open(filename, "w") as fh:
                    fh.write(content)
                msg = f"File created:{filename}"
            except Exception as ex:
                msg = f"File write failed:{filename} ({ex})"

            writer.write(_reply(now, [msg], cfg["uid_key"]))
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            classes.Err("Info:Disconnected " + str(addr))
            return

        if ftype == "delete" and filename:
            try:
                os.remove(filename)
                msg = f"File deleted:{filename}"
            except Exception as ex:
                msg = f"File delete failed:{filename} ({ex})"

            writer.write(_reply(now, [msg], cfg["uid_key"]))
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            classes.Err("Info:Disconnected " + str(addr))
            return

        if "command" in data:
            cmd = base64.b64decode(data["command"]).decode("utf-8", errors="strict")
            rc, out = await _run_command(cmd, cfg["allowed_cmds"])

            sanitized = re.sub(
                r'("?(?:pwd|pass|password|srvpass|cpass|chlpass)"?\s*:\s*)(".*?"|\'.*?\'|[^,\}\s]+)',
                r'\1"..."',
                cmd,
                flags=re.IGNORECASE,
            )

            classes.Err("Command:" + sanitized + " from " + str(addr))
            writer.write(
                _reply(
                    now,
                    ["Command:" + sanitized, "RC:" + str(rc), "Output:" + out],
                    cfg["uid_key"],
                )
            )
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            classes.Err("Info:Disconnected " + str(addr))
            return

        writer.write(_reply(now, ["Command:empty!"], cfg["uid_key"]))
        await writer.drain()
        writer.close()
        await writer.wait_closed()
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
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def main():
    classes.ClearLog()
    server = await asyncio.start_server(
        handle_client, host="", port=PORT_NUMBER, backlog=100
    )
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
