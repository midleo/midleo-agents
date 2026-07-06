import base64
import binascii
import xml.etree.ElementTree as ET

from modules.base import classes
from modules.message_backup.provider import MessageBackupProvider
from modules.statistics.ibmmq import ibmmq

try:
    import pymqi
    MQ_ERROR = pymqi.MQMIError
except ImportError:
    pymqi = None
    MQ_ERROR = Exception

_MQRFH_STRUC_ID = b"RFH "
_MQHRF2_FORMAT = "MQHRF2  "


def _hex_bytes(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return binascii.hexlify(value).decode("ascii")
    text = str(value).strip()
    if not text:
        return ""
    if all(c in "0123456789abcdefABCDEF" for c in text):
        return text.lower()
    return binascii.hexlify(text.encode("utf-8", errors="replace")).decode("ascii")


def _safe_mq_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        try:
            null_index = value.find(0)
            if null_index != -1:
                value = value[:null_index]
            return value.decode("utf-8", errors="replace").strip()
        except Exception:
            return _hex_bytes(value)
    return str(value).strip().replace("\u0000", "")


def _safe_mq_format(value):
    text = _safe_mq_text(value)
    return text.strip()


def _json_safe_property(value):
    if isinstance(value, dict):
        return {_safe_mq_text(k): _json_safe_property(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_property(item) for item in value]
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return _hex_bytes(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return _safe_mq_text(value)


def _md_field(md, name, transform=None):
    if md is None:
        return None
    try:
        value = getattr(md, name)
    except Exception:
        return None
    if transform is not None:
        return transform(value)
    return value


def _extract_mqmd_fields(md):
    fields = {
        "Version": _md_field(md, "Version"),
        "Report": _md_field(md, "Report"),
        "MsgType": _md_field(md, "MsgType"),
        "MsgId": _md_field(md, "MsgId", _hex_bytes),
        "CorrelId": _md_field(md, "CorrelId", _hex_bytes),
        "PutDate": _safe_mq_text(_md_field(md, "PutDate")),
        "PutTime": _safe_mq_text(_md_field(md, "PutTime")),
        "Format": _safe_mq_format(_md_field(md, "Format")),
        "ReplyToQ": _safe_mq_text(_md_field(md, "ReplyToQ")),
        "ReplyToQMgr": _safe_mq_text(_md_field(md, "ReplyToQMgr")),
        "Priority": _md_field(md, "Priority"),
        "Persistence": _md_field(md, "Persistence"),
        "Expiry": _md_field(md, "Expiry"),
        "Feedback": _md_field(md, "Feedback"),
        "BackoutCount": _md_field(md, "BackoutCount"),
        "PutApplType": _md_field(md, "PutApplType"),
        "PutApplName": _safe_mq_text(_md_field(md, "PutApplName")),
        "ApplOriginData": _safe_mq_text(_md_field(md, "ApplOriginData")),
        "UserIdentifier": _safe_mq_text(_md_field(md, "UserIdentifier")),
        "Encoding": _md_field(md, "Encoding"),
        "CodedCharSetId": _md_field(md, "CodedCharSetId"),
        "ApplIdentityData": _safe_mq_text(_md_field(md, "ApplIdentityData")),
        "GroupId": _md_field(md, "GroupId", _hex_bytes),
        "MsgSeqNumber": _md_field(md, "MsgSeqNumber"),
        "Offset": _md_field(md, "Offset"),
    }
    msg_id = fields.get("MsgId") or ""
    correl = fields.get("CorrelId") or ""
    fields["message_id"] = msg_id
    fields["correlationId"] = correl
    return fields


def _message_handle_supported():
    return pymqi is not None and hasattr(pymqi, "MessageHandle")


def _message_handle_get_handle(msg_h):
    if hasattr(msg_h, "get_handle"):
        return msg_h.get_handle()
    return getattr(msg_h, "msg_handle", None)


def _build_gmo(qmgr, timeout_ms):
    gmo = pymqi.GMO()
    gmo.Options = (
        pymqi.CMQC.MQGMO_WAIT
        | pymqi.CMQC.MQGMO_CONVERT
        | getattr(pymqi.CMQC, "MQGMO_SYNCPOINT", 0)
        | getattr(pymqi.CMQC, "MQGMO_FAIL_IF_QUIESCING", 0)
    )
    gmo.WaitInterval = max(100, int(timeout_ms))
    msg_h = None
    if _message_handle_supported():
        try:
            gmo.Version = getattr(pymqi.CMQC, "MQGMO_CURRENT_VERSION", gmo.Version)
            msg_h = pymqi.MessageHandle(qmgr)
            gmo.Options |= getattr(pymqi.CMQC, "MQGMO_PROPERTIES_IN_HANDLE", 0)
            gmo.MsgHandle = _message_handle_get_handle(msg_h)
        except Exception:
            msg_h = None
    return gmo, msg_h


def _iter_message_properties(msg_h):
    properties = {}
    if pymqi is None or msg_h is None or not hasattr(msg_h, "properties"):
        return properties

    opts = getattr(pymqi.CMQC, "MQIMPO_INQ_FIRST", 0)
    while True:
        try:
            value, name = msg_h.properties.get("%", impo_options=opts)
        except MQ_ERROR as ex:
            reason = ex.args[1] if len(ex.args) >= 2 else 0
            if reason == getattr(pymqi.CMQC, "MQRC_PROPERTY_NOT_AVAILABLE", -1):
                break
            break
        except Exception:
            break
        key = _safe_mq_text(name)
        if key:
            properties[key] = _json_safe_property(value)
        opts = getattr(pymqi.CMQC, "MQIMPO_INQ_NEXT", opts)

    return properties


def _xml_element_to_value(element):
    children = list(element)
    if not children:
        text = (element.text or "").strip()
        return text
    if len(children) == 1 and not (element.text or "").strip():
        return _xml_element_to_value(children[0])
    result = {}
    for child in children:
        tag = child.tag.split("}", 1)[-1]
        value = _xml_element_to_value(child)
        if tag in result:
            existing = result[tag]
            if not isinstance(existing, list):
                existing = [existing]
            existing.append(value)
            result[tag] = existing
        else:
            result[tag] = value
    return result


def _parse_rfh2_folder(folder_bytes):
    if not folder_bytes:
        return {}
    if isinstance(folder_bytes, bytes):
        try:
            null_index = folder_bytes.find(0)
            if null_index != -1:
                folder_bytes = folder_bytes[:null_index]
            folder_text = folder_bytes.decode("utf-8", errors="replace").strip()
        except Exception:
            return {"_raw": _hex_bytes(folder_bytes)}
    else:
        folder_text = str(folder_bytes).strip()
    if not folder_text:
        return {}
    try:
        root = ET.fromstring(folder_text)
    except ET.ParseError:
        return {"_raw": folder_text}
    tag = root.tag.split("}", 1)[-1]
    parsed = _xml_element_to_value(root)
    if isinstance(parsed, dict):
        return parsed
    return {tag: parsed}


def _is_rfh2_message(md, body):
    fmt = _safe_mq_format(_md_field(md, "Format"))
    if fmt.strip() == _MQHRF2_FORMAT.strip() or fmt == "MQHRF2":
        return True
    if isinstance(body, (bytes, bytearray)) and len(body) >= 4:
        return bytes(body[:4]) == _MQRFH_STRUC_ID
    return False


def _parse_rfh2(body, md):
    result = {
        "folders": {},
        "headers": {},
        "properties": {},
        "application_body": body,
    }
    if pymqi is None or not hasattr(pymqi, "RFH2"):
        return result
    if not isinstance(body, (bytes, bytearray)) or len(body) < 36:
        return result

    try:
        rfh2 = pymqi.RFH2()
        encoding = _md_field(md, "Encoding")
        rfh2.unpack(bytes(body), encoding=encoding)
    except Exception:
        return result

    header_len = int(rfh2.get("StrucLength") or 0)
    if header_len > 0 and header_len < len(body):
        result["application_body"] = bytes(body[header_len:])

    for folder_name in rfh2.get_folders():
        folder_data = rfh2.get(folder_name)
        parsed = _parse_rfh2_folder(folder_data)
        result["folders"][folder_name] = parsed
        if folder_name in ("mcd", "jms", "usr"):
            result["headers"][folder_name] = parsed
        if isinstance(parsed, dict):
            for key, value in parsed.items():
                if key.startswith("_"):
                    continue
                prop_key = key
                if folder_name == "jms" and not key.startswith("JMS"):
                    prop_key = "JMS" + key
                result["properties"][prop_key] = value

    return result


def _split_body_for_envelope(body, md, body_mode):
    if body_mode == "none" or body is None:
        return None, {}, {}
    if not _is_rfh2_message(md, body):
        return body, {}, {}
    parsed = _parse_rfh2(body, md)
    return parsed.get("application_body", body), parsed.get("headers", {}), parsed.get("properties", {})


class IbmMqMessageBackupProvider(MessageBackupProvider):
    def __init__(self, job_cfg, broker_cfg):
        self.job_cfg = dict(job_cfg or {})
        self.broker_cfg = dict(broker_cfg or {})
        self.qmgr_name = str(
            self.job_cfg.get("middleware_instance")
            or self.broker_cfg.get("qmgr")
            or self.broker_cfg.get("appsrv")
            or ""
        )
        self.queue_name = str(self.job_cfg.get("source") or "")
        self.qmgr = None
        self.queue = None
        self._pending = []
        self._msg_handles = []

    def connect(self):
        if pymqi is None:
            raise RuntimeError("pymqi is not available")
        self.qmgr = ibmmq.connect_qmgr(self.broker_cfg, self.qmgr_name)
        if self.qmgr is None:
            raise RuntimeError("IBM MQ connect failed for " + self.qmgr_name)
        self.queue = pymqi.Queue(self.qmgr, self.queue_name)

    def check_health(self):
        return self.qmgr is not None and self.queue is not None

    def receive(self, max_messages, timeout_ms, body_mode):
        if not self.check_health():
            return
        fetched = 0
        while fetched < max_messages:
            msg_h = None
            try:
                gmo, msg_h = _build_gmo(self.qmgr, timeout_ms)
                md = pymqi.MD()
                body = self.queue.get(None, md, gmo)
            except MQ_ERROR as ex:
                comp, reason = ex.args if len(ex.args) >= 2 else (0, 0)
                if reason in (
                    pymqi.CMQC.MQRC_NO_MSG_AVAILABLE,
                    pymqi.CMQC.MQRC_NO_MSG_UNDER_CURSOR,
                ):
                    break
                classes.Err("ibmmq message_backup receive failed:" + str(ex))
                break
            finally:
                if msg_h is not None and msg_h not in self._msg_handles:
                    self._msg_handles.append(msg_h)

            fetched += 1
            raw = _extract_mqmd_fields(md)
            mq_properties = _iter_message_properties(msg_h)
            body_for_envelope, rfh_headers, rfh_properties = _split_body_for_envelope(
                body, md, body_mode
            )

            properties = dict(mq_properties)
            properties.update(rfh_properties)
            for key, value in raw.items():
                if key.startswith("_") or key in ("message_id", "correlationId"):
                    continue
                properties.setdefault(key, value)
            correl = raw.get("CorrelId") or ""
            if correl:
                properties.setdefault("correlationId", correl)

            headers = dict(rfh_headers)
            if raw.get("Format"):
                headers.setdefault("Format", raw.get("Format"))
            if properties.get("rfh2"):
                headers.setdefault("rfh2", properties.get("rfh2"))

            item = {
                "raw": dict(raw, _md=md),
                "body": body_for_envelope if body_mode != "none" else None,
                "properties": properties,
                "headers": headers,
                "delivery_metadata": {
                    "queue": self.queue_name,
                    "format": raw.get("Format") or "",
                    "rfh2": bool(rfh_headers or rfh_properties),
                },
                "message_id": raw.get("MsgId") or "",
                "timestamp": str(raw.get("PutDate", "")) + " " + str(raw.get("PutTime", "")),
            }
            self._pending.append((md, item))
            yield item

    def _commit(self):
        if self.qmgr is not None:
            self.qmgr.commit()

    def _backout(self):
        if self.qmgr is not None:
            self.qmgr.backout()

    def ack(self, message):
        handle = message.get("_raw_handle") if isinstance(message, dict) else message
        if isinstance(handle, dict) and handle.get("_md") is not None:
            self._commit()
            self._pending = [item for item in self._pending if item[1].get("raw") is not handle]
            return
        self._commit()
        self._pending = []

    def nack(self, message, requeue=True):
        if self.check_health():
            try:
                self._backout()
            except Exception as err:
                classes.Err("ibmmq message_backup backout failed:" + str(err))
        if not requeue:
            classes.Err("ibmmq message_backup nack: message backed out; discard is not supported safely")
        self._pending = []

    def close(self):
        for msg_h in self._msg_handles:
            try:
                if hasattr(msg_h, "dlt"):
                    msg_h.dlt()
            except Exception:
                pass
        self._msg_handles = []
        if self._pending and self.check_health():
            try:
                self._backout()
            except Exception as err:
                classes.Err("ibmmq message_backup close backout failed:" + str(err))
            self._pending = []
        if self.queue is not None:
            try:
                self.queue.close()
            except Exception:
                pass
            self.queue = None
        if self.qmgr is not None:
            ibmmq.qmDisc(self.qmgr)
            self.qmgr = None
